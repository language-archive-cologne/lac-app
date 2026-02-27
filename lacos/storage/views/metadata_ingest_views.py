import json
import logging

from lacos.storage.permissions import archivist_required
from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from lacos.ingest.tasks import import_s3_collection, import_s3_bundle, process_s3_prefix
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin

logger = logging.getLogger(__name__)


def validate_metadata_xml(bucket: str, s3_key: str, metadata_type: str) -> dict:
    """
    Validate XML file before importing.

    Returns dict with:
        - 'valid': bool
        - 'error': str (if invalid)
        - 'warnings': list of str
        - 'details': dict with metadata info
    """
    from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
    from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
    from django.core.exceptions import ValidationError

    result = {
        'valid': False,
        'error': None,
        'warnings': [],
        'details': {}
    }

    # Check if file exists in S3
    try:
        logger.info("VALIDATE_XML: Reading S3 object", extra={"bucket": bucket, "key": s3_key})
        discovery_service = FileDiscoveryService()
        xml_bytes = discovery_service.read_s3_object(bucket=bucket, key=s3_key)

        if not xml_bytes:
            logger.warning("VALIDATE_XML: File not found")
            result['error'] = f"File not found in bucket '{bucket}' at path '{s3_key}'"
            return result

        logger.info("VALIDATE_XML: Successfully read S3 object", extra={"byte_count": len(xml_bytes)})

    except Exception as e:
        logger.error("VALIDATE_XML: Error reading S3 object", extra={"error": str(e)}, exc_info=True)
        result['error'] = f"Cannot access S3 file: {str(e)}"
        return result

    # Try to decode XML
    try:
        xml_content = xml_bytes.decode('utf-8')
    except UnicodeDecodeError as e:
        result['error'] = f"File is not valid UTF-8 text: {str(e)}"
        return result

    # Validate XML structure using xsdata importers
    try:
        if metadata_type == 'collection':
            cmd_data = CollectionImporter.validate_xml(xml_content)

            # Extract useful info for display
            if hasattr(cmd_data, 'header') and cmd_data.header:
                if hasattr(cmd_data.header, 'md_self_link'):
                    identifier = cmd_data.header.md_self_link.value
                    result['details']['identifier'] = identifier

                    # Check if already exists
                    from lacos.blam.models.collection.collection_repository import Collection
                    existing = Collection.objects.filter(identifier=identifier).first()
                    if existing:
                        result['warnings'].append(
                            f"Collection '{identifier}' already exists in database. "
                            f"Import will skip this collection."
                        )

            result['details']['version'] = cmd_data.version
            result['details']['type'] = 'Collection'

        else:  # bundle
            cmd_data = BundleImporter.validate_xml(xml_content)

            # Extract useful info for display
            if hasattr(cmd_data, 'header') and cmd_data.header:
                if hasattr(cmd_data.header, 'md_self_link'):
                    identifier = cmd_data.header.md_self_link.value
                    result['details']['identifier'] = identifier

                    # Check if already exists
                    from lacos.blam.models.bundle.bundle_repository import Bundle
                    existing = Bundle.objects.filter(identifier=identifier).first()
                    if existing:
                        result['warnings'].append(
                            f"Bundle '{identifier}' already exists in database. "
                            f"Import will skip this bundle."
                        )

            result['details']['type'] = 'Bundle'

        result['valid'] = True

    except ValidationError as e:
        # This is the xsdata validation error - make it user-friendly
        error_msg = str(e)

        # Parse common xsdata errors and make them readable
        if "No matching global declaration" in error_msg:
            result['error'] = (
                "XML structure doesn't match BLAM schema. "
                "The root element or namespace might be incorrect."
            )
        elif "is not valid" in error_msg:
            result['error'] = f"XML validation failed: {error_msg}"
        elif "Expected element" in error_msg:
            result['error'] = (
                f"Missing required XML element. {error_msg}"
            )
        else:
            result['error'] = f"Invalid BLAM {metadata_type} XML: {error_msg}"

    except Exception as e:
        result['error'] = f"Unexpected error parsing XML: {str(e)}"

    return result


@archivist_required
def metadata_ingest_modal(request, bucket_type, object_type, object_path):
    """Render the metadata ingest modal with sensible defaults."""

    bucket_service = BucketService()
    accessible_buckets = bucket_service.get_all_accessible_buckets()

    if bucket_type in accessible_buckets:
        bucket_name = bucket_type
    elif bucket_type == 'ingest':
        bucket_name = bucket_service.ingest_bucket
    elif bucket_type == 'production':
        bucket_name = bucket_service.production_bucket
    else:
        bucket_name = bucket_type

    object_type = object_type if object_type in {"file", "folder"} else "file"

    clean_path = object_path.rstrip('/')
    if object_type == 'file':
        initial_key = clean_path
    else:
        initial_key = f"{clean_path}/" if clean_path else ''

    lower_path = clean_path.lower()
    default_type = 'bundle' if 'bundle' in lower_path else 'collection'

    if bucket_name not in accessible_buckets:
        accessible_buckets = sorted({*accessible_buckets, bucket_name})

    context = {
        'bucket_options': accessible_buckets,
        'current_bucket': bucket_name,
        'initial_key': initial_key,
        'default_metadata_type': default_type,
        'object_type': object_type,
    }

    return render(request, 'storage/metadata_ingest_modal.html', context)


@require_POST
@archivist_required
def ingest_metadata(request):
    """Queue a metadata XML ingestion task for a collection or bundle."""

    is_htmx = request.headers.get('HX-Request') == 'true'

    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body.decode("utf-8") or "{}")
        else:
            payload = request.POST
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse metadata ingest payload: %s", exc)
        if is_htmx:
            return _render_modal_with_error(request, payload={}, error="Invalid JSON payload")
        return JsonResponse({"success": False, "error": "Invalid JSON payload"}, status=400)

    metadata_type = (payload.get("metadata_type") or "").strip().lower()
    bucket = (payload.get("bucket") or "").strip()
    s3_key = (payload.get("s3_key") or "").strip()
    use_pipeline = (payload.get('use_pipeline') or '').strip().lower() == 'true'
    pipeline_prefix = (payload.get('pipeline_prefix') or '').strip()
    preview_collection_count = int((payload.get('preview_collection_count') or '0').strip() or 0)
    preview_bundle_count = int((payload.get('preview_bundle_count') or '0').strip() or 0)
    update_existing = _parse_bool(payload.get('update_existing'))

    if metadata_type not in {"collection", "bundle"}:
        error_message = "metadata_type must be 'collection' or 'bundle'"
        if is_htmx:
            return _render_modal_with_error(request, payload=payload, error=error_message)
        return JsonResponse({"success": False, "error": error_message}, status=400)

    if not bucket or not s3_key:
        error_message = "bucket and s3_key are required"
        if is_htmx:
            return _render_modal_with_error(request, payload=payload, error=error_message)
        return JsonResponse({"success": False, "error": error_message}, status=400)

    try:
        if use_pipeline:
            if not pipeline_prefix:
                raise ValueError('Pipeline preview data missing. Please preview again.')

            logger.info(
                "Launching collection ingest pipeline",
                extra={
                    "bucket": bucket,
                    "prefix": pipeline_prefix,
                    "preview_collection_count": preview_collection_count,
                    "preview_bundle_count": preview_bundle_count,
                },
            )
            process_s3_prefix(
                bucket=bucket,
                prefix=pipeline_prefix,
                update_existing=update_existing,
            )
            task = None
        elif metadata_type == "collection":
            # Always use pipeline to ensure S3 resource locations are updated
            # Extract the collection folder prefix from the path
            if s3_key.endswith('.xml'):
                # Extract folder from XML path (e.g., "coll/coll/v1/content/coll.xml" -> "coll/")
                parts = s3_key.split('/')
                prefix = f"{parts[0]}/"
            else:
                # Folder path provided
                collection_id = s3_key.rstrip('/').split('/')[-1]
                prefix = f"{collection_id}/"

            logger.info(
                "Launching collection pipeline",
                extra={
                    "bucket": bucket,
                    "original_key": s3_key,
                    "prefix": prefix,
                    "update_existing": update_existing,
                },
            )
            process_s3_prefix(
                bucket=bucket,
                prefix=prefix,
                update_existing=update_existing,
            )
            task = None
        else:
            # If s3_key is a folder path for bundle, form the proper OCFL XML path
            actual_s3_key = s3_key
            if s3_key.endswith('/') or not s3_key.endswith('.xml'):
                discovery_service = FileDiscoveryService()
                # Extract collection_id and bundle_id from path (e.g., "collection/bundle/" -> collection, bundle)
                parts = s3_key.rstrip('/').split('/')
                if len(parts) >= 2:
                    collection_id = parts[-2]
                    bundle_id = parts[-1]
                    actual_s3_key = discovery_service.form_bundle_xml_path(collection_id, bundle_id)
                    logger.info(
                        "Formed OCFL bundle XML path from folder",
                        extra={
                            "original_key": s3_key,
                            "collection_id": collection_id,
                            "bundle_id": bundle_id,
                            "formed_xml_path": actual_s3_key,
                        },
                    )
            task = import_s3_bundle(
                bucket=bucket,
                s3_key=actual_s3_key,
                update_existing=update_existing,
            )

        task_id = getattr(task, "id", None)

        logger.info(
            "Queued metadata ingest task",
            extra={
                "metadata_type": metadata_type,
                "bucket": bucket,
                "s3_key": s3_key,
                "task_id": task_id,
                "use_pipeline": use_pipeline,
                "pipeline_prefix": pipeline_prefix if use_pipeline else None,
                "update_existing": update_existing,
            },
        )

        if is_htmx:
            response = render(
                request,
                'storage/metadata_ingest_result.html',
                {
                    'bucket': bucket,
                    's3_key': s3_key,
                    'metadata_type': metadata_type,
                    'task_id': task_id,
                    'used_pipeline': use_pipeline,
                    'pipeline_prefix': pipeline_prefix,
                    'preview_collection_count': preview_collection_count,
                    'preview_bundle_count': preview_bundle_count,
                    'update_existing': update_existing,
                },
            )
            if use_pipeline:
                verb = "reindex" if update_existing else "ingest"
                message = f"Collection {verb} pipeline queued for prefix {pipeline_prefix or s3_key} in {bucket}."
            else:
                verb = "reindex" if update_existing else "ingest"
                message = f"Metadata {verb} queued for {s3_key} (bucket {bucket})."

            response['HX-Trigger'] = json.dumps({
                'showMessage': {
                    'message': message,
                    'level': 'success',
                }
            })
            return response

        return JsonResponse({
            "success": True,
            "task_id": task_id,
            "used_pipeline": use_pipeline,
            "pipeline_prefix": pipeline_prefix,
            "update_existing": update_existing,
        })

    except Exception as exc:
        logger.error("Failed to queue metadata ingest task: %s", exc, exc_info=True)
        if is_htmx:
            return _render_modal_with_error(request, payload=payload, error=str(exc))
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@archivist_required
def validate_metadata_endpoint(request, bucket_type, object_path):
    """
    Validate a specific XML file and return results via HTMX.
    """
    from django.utils.text import slugify

    # Clean up trailing slashes from path
    object_path = object_path.rstrip('/')

    logger.info("VALIDATE: Starting validation", extra={"bucket_type": bucket_type, "object_path": object_path})

    bucket_service = BucketService()
    accessible_buckets = bucket_service.get_all_accessible_buckets()

    # Determine actual bucket name
    if bucket_type in accessible_buckets:
        bucket_name = bucket_type
    elif bucket_type == 'ingest':
        bucket_name = bucket_service.ingest_bucket
    elif bucket_type == 'production':
        bucket_name = bucket_service.production_bucket
    else:
        bucket_name = bucket_type

    logger.info("VALIDATE: Resolved bucket name", extra={"bucket_name": bucket_name})

    # Get metadata type from query parameter (user explicitly selected it)
    metadata_type = request.GET.get('type', '').lower()

    # Validate the type parameter
    if metadata_type not in ['collection', 'bundle']:
        # Fallback to auto-detection if not specified
        lower_path = object_path.lower()

        # First check if path explicitly contains 'collection' or 'bundle'
        if 'collection' in lower_path:
            metadata_type = 'collection'
        elif 'bundle' in lower_path:
            metadata_type = 'bundle'
        else:
            # Heuristic: if the first two path segments are the same, likely a collection
            path_parts = object_path.split('/')
            if len(path_parts) >= 2 and path_parts[0] == path_parts[1]:
                metadata_type = 'collection'
            else:
                metadata_type = 'bundle'

        logger.info("VALIDATE: Auto-detected metadata type", extra={"metadata_type": metadata_type, "object_path": object_path})
    else:
        logger.info("VALIDATE: User-selected metadata type", extra={"metadata_type": metadata_type})

    # Get or generate target_id for proper element replacement
    target_id = request.GET.get('target_id') or slugify(f'file-info-{object_path}')

    logger.info("VALIDATE: Using target ID", extra={"target_id": target_id})

    # Run validation
    result = validate_metadata_xml(bucket_name, object_path, metadata_type)

    logger.info("VALIDATE: Validation complete", extra={"valid": result.get('valid'), "error": result.get('error')})

    context = {
        'result': result,
        'bucket': bucket_name,
        's3_key': object_path,
        'metadata_type': metadata_type,
        'target_id': target_id,
    }

    if request.headers.get('HX-Request') == 'true':
        helper = HtmxTemplateHelperMixin()
        validation_html = render_to_string(
            'storage/metadata_validation_result.html',
            context,
            request=request,
        )

        message_level = 'success' if result.get('valid') else 'error'
        message_label = 'validated' if result.get('valid') else 'failed validation'
        message = f"{metadata_type.title()} XML {message_label} for {object_path}"

        message_body = helper.render_message_template(message, level=message_level)
        if '<div class="alert' in message_body:
            message_body = message_body.replace('<div class="alert', '<div id="message-content" class="alert', 1)

        # Main response is validation_html (targeted by hx-target)
        # Message uses OOB to update the message container
        oob_updates = {
            'message-container': f'<div class="mb-6">{message_body}</div>'
        }

        response_html = helper.build_oob_response(validation_html, oob_updates)

        triggers = {
            'showMessage': {
                'message': message,
                'level': message_level,
            }
        }

        return helper.add_htmx_trigger(response_html, triggers)

    return render(request, 'storage/metadata_validation_result.html', context)


def _render_modal_with_error(request, payload, error):
    """Re-render the modal with an error message for HTMX requests."""

    bucket_service = BucketService()
    accessible_buckets = bucket_service.get_all_accessible_buckets()

    current_bucket = (payload.get('bucket') or '').strip()
    if not current_bucket:
        current_bucket = bucket_service.ingest_bucket

    if current_bucket not in accessible_buckets:
        accessible_buckets = sorted({*accessible_buckets, current_bucket})

    requested_type = (payload.get('object_type', 'file') or 'file').lower()
    if requested_type not in {"file", "folder"}:
        requested_type = 'file'

    default_type = (payload.get('metadata_type') or 'bundle').strip().lower()
    if default_type not in {"bundle", "collection"}:
        default_type = 'bundle'

    context = {
        'bucket_options': accessible_buckets,
        'current_bucket': current_bucket,
        'initial_key': (payload.get('s3_key') or '').strip(),
        'default_metadata_type': default_type,
        'object_type': requested_type,
        'error_message': error,
    }

    response = render(request, 'storage/metadata_ingest_modal.html', context, status=400)
    response['HX-Trigger'] = json.dumps({
        'showMessage': {
            'message': error,
            'level': 'error',
        }
    })
    return response


def _infer_pipeline_prefix(object_type: str, s3_key: str) -> str:
    """Infer the prefix used to discover related BLAM XML files."""
    clean_key = (s3_key or '').strip('/ ')
    if not clean_key:
        return ''

    if object_type == 'folder':
        return f"{clean_key}/"

    parts = clean_key.split('/')
    if len(parts) <= 1:
        return ''
    return f"{parts[0]}/"


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


@archivist_required
def preview_metadata_ingest(request):
    """Return a preview of the metadata ingest that would be enqueued."""

    bucket = (request.GET.get('bucket') or '').strip()
    s3_key = (request.GET.get('s3_key') or '').strip()
    object_type = (request.GET.get('object_type') or 'file').strip().lower()
    metadata_type = (request.GET.get('metadata_type') or '').strip().lower()
    update_existing = _parse_bool(request.GET.get('update_existing'))

    logger.info(
        "Preview metadata ingest requested",
        extra={
            "bucket": bucket,
            "s3_key": s3_key,
            "object_type": object_type,
            "metadata_type": metadata_type,
            "update_existing": update_existing,
        },
    )

    context = {
        'bucket': bucket,
        's3_key': s3_key,
        'metadata_type': metadata_type,
        'object_type': object_type,
        'update_existing': update_existing,
    }

    if not bucket or not s3_key:
        context['error_message'] = 'Bucket and S3 key are required to build a preview.'
        return render(request, 'storage/metadata_ingest_preview.html', context)

    prefix = _infer_pipeline_prefix(object_type, s3_key)
    logger.debug(
        "Inferred pipeline prefix for ingest preview",
        extra={"prefix": prefix},
    )

    if metadata_type == 'bundle':
        # Bundle imports operate on the single XML the user selected.
        context.update({
            'collection_xmls': [],
            'bundle_xmls': [s3_key],
            'should_use_pipeline': False,
            'pipeline_prefix': '',
            'collection_count': 0,
            'bundle_count': 1,
        })
        return render(request, 'storage/metadata_ingest_preview.html', context)

    if not prefix:
        context['error_message'] = 'Unable to infer the collection prefix for discovery. Try selecting the top-level folder instead.'
        logger.warning(
            "Unable to infer collection prefix for ingest preview",
            extra={"bucket": bucket, "s3_key": s3_key, "object_type": object_type},
        )
        return render(request, 'storage/metadata_ingest_preview.html', context)

    discovery_service = FileDiscoveryService()
    try:
        discovery_result = discovery_service.find_collection_and_bundle_xmls_s3(bucket, prefix=prefix)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error('Failed to preview metadata ingest for %s/%s: %s', bucket, s3_key, exc, exc_info=True)
        context['error_message'] = 'Error while scanning S3 for BLAM XML files.'
        return render(request, 'storage/metadata_ingest_preview.html', context)

    collection_xmls = discovery_result.get('potential_collection_xmls', [])
    bundle_xmls = discovery_result.get('potential_bundle_xmls', [])

    if not collection_xmls:
        context['error_message'] = 'No collection XML could be located under the inferred prefix.'
        logger.warning(
            "No collection XML discovered under prefix",
            extra={
                "bucket": bucket,
                "prefix": prefix,
                "bundle_candidates": bundle_xmls,
            },
        )
        return render(request, 'storage/metadata_ingest_preview.html', context)

    logger.info(
        "Metadata ingest discovery result",
        extra={
            "bucket": bucket,
            "prefix": prefix,
            "collection_count": len(collection_xmls),
            "bundle_count": len(bundle_xmls),
        },
    )

    context.update({
        'collection_xmls': collection_xmls,
        'bundle_xmls': bundle_xmls,
        'should_use_pipeline': True,
        'pipeline_prefix': prefix,
        'collection_count': len(collection_xmls),
        'bundle_count': len(bundle_xmls),
    })
    return render(request, 'storage/metadata_ingest_preview.html', context)
