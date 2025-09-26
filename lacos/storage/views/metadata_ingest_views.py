import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from lacos.ingest.tasks import import_s3_collection, import_s3_bundle
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@login_required
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
    default_type = 'collection' if 'collection' in lower_path else 'bundle'

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
@login_required
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
        if metadata_type == "collection":
            task = import_s3_collection(bucket=bucket, s3_key=s3_key)
        else:
            task = import_s3_bundle(bucket=bucket, s3_key=s3_key)

        task_id = getattr(task, "id", None)

        logger.info(
            "Queued metadata ingest task",
            extra={
                "metadata_type": metadata_type,
                "bucket": bucket,
                "s3_key": s3_key,
                "task_id": task_id,
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
                },
            )
            response['HX-Trigger'] = json.dumps({
                'showMessage': {
                    'message': f"Metadata ingest queued for {s3_key} (bucket {bucket}).",
                    'level': 'success',
                }
            })
            return response

        return JsonResponse({"success": True, "task_id": task_id})

    except Exception as exc:
        logger.error("Failed to queue metadata ingest task: %s", exc, exc_info=True)
        if is_htmx:
            return _render_modal_with_error(request, payload=payload, error=str(exc))
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


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
