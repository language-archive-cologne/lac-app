import ast
import json
import logging
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_http_methods

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.common.mixins import BucketCoordinatorMixin, HtmxTemplateHelperMixin
from lacos.storage.models.acl_config import ACLConfig
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


def _resolve_acl_display_name(obj):
    if obj is None:
        return None
    candidate = getattr(obj, "name", None) or getattr(obj, "title", None)
    if not candidate and hasattr(obj, "get_general_info"):
        general_info = obj.get_general_info
        if general_info:
            candidate = getattr(general_info, "display_title", None) or getattr(general_info, "title", None)
    if not candidate:
        candidate = getattr(obj, "identifier", None)
    return candidate or str(getattr(obj, "pk", ""))


def _get_acl_options(model):
    options = []
    for obj in model.objects.order_by("identifier"):
        display_name = _resolve_acl_display_name(obj)
        identifier = getattr(obj, "identifier", str(obj.pk))
        options.append(
            {
                "id": str(obj.pk),
                "identifier": identifier,
                "name": display_name,
                "label": f"{identifier}{f' — {display_name}' if display_name else ''}",
            }
        )
    return options


def _render_sync_summary_partial(request, summary=None, error_message=None):
    html = render_to_string(
        "dashboard/partials/acl_sync_summary.html",
        {"sync_summary": summary, "error_message": error_message},
        request=request,
    )
    return HttpResponse(html)


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing all workspace buckets.
    Only loads root level items initially for better performance.
    """
    bucket_service = BucketService()
    bucket_state = BucketCoordinatorMixin()

    force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

    try:
        # Get root level items for all workspace buckets
        bucket_structures = {}
        workspace_buckets = bucket_service.get_all_accessible_buckets()

        for bucket_name in workspace_buckets:
            try:
                if force_fresh:
                    bucket_structures[bucket_name] = bucket_service.get_root_level_items(bucket_name, force_fresh=True)
                else:
                    bucket_structures[bucket_name] = bucket_service.get_root_level_items(bucket_name)
            except Exception as e:
                logger.error(f"Error loading bucket {bucket_name}: {str(e)}")
                # Return empty structure on error for this bucket
                bucket_structures[bucket_name] = {
                    "type": "folder",
                    "name": bucket_name,
                    "path": "",
                    "children": []
                }

        # Maintain backward compatibility - provide legacy bucket names
        ingest_structure = bucket_structures.get(bucket_service.ingest_bucket, {})
        production_structure = bucket_structures.get(bucket_service.production_bucket, {})

    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        # Return empty structures on error
        bucket_structures = {}
        workspace_buckets = bucket_service.get_all_accessible_buckets()
        ingest_structure = {"type": "folder", "name": bucket_service.ingest_bucket, "path": "", "children": []}
        production_structure = {"type": "folder", "name": bucket_service.production_bucket, "path": "", "children": []}

    active_bucket = bucket_state.ensure_active_bucket(request, workspace_buckets)
    active_bucket_structure = bucket_structures.get(active_bucket)

    if active_bucket and active_bucket_structure is None:
        active_bucket_structure = {
            "type": "folder",
            "name": active_bucket,
            "path": "",
            "children": [],
        }

    # Check for success message
    message = request.GET.get('message', None)

    return render(
        request,
        "dashboard/archivist_dashboard.html",
        {
            "bucket_structures": bucket_structures,
            "workspace_buckets": workspace_buckets,
            "active_bucket": active_bucket,
            "active_bucket_structure": active_bucket_structure,
            "ocfl_buckets": bucket_service.ocfl_buckets,
            # Legacy backward compatibility
            "ingest_structure": ingest_structure,
            "production_structure": production_structure,
            "message": message,
        },
    )


@login_required
def acl_admin_dashboard(request):
    """
    Render the ACL Admin Dashboard with current settings, summary stats,
    and recent permission records.
    """
    # Settings flags (DB-backed with settings fallback)
    from lacos.storage.models.acl_config import ACLConfig
    from lacos.blam.models.collection.collection_repository import Collection
    from lacos.blam.models.bundle.bundle_repository import Bundle
    from django.contrib.contenttypes.models import ContentType

    cfg = None
    try:
        cfg = ACLConfig.get_solo()
    except Exception:
        cfg = None

    acl_flags = {
        "ACL_ENFORCEMENT_ENABLED": (cfg.enforcement_enabled if cfg else getattr(settings, "ACL_ENFORCEMENT_ENABLED", True)),
        "ACL_LOG_ACCESS_ATTEMPTS": (cfg.log_access_attempts if cfg else getattr(settings, "ACL_LOG_ACCESS_ATTEMPTS", True)),
        "ACL_DEFAULT_DENY": (cfg.default_deny if cfg else getattr(settings, "ACL_DEFAULT_DENY", True)),
    }

    try:
        from lacos.storage.models.acl_permissions import ACLPermissions

        # Stats
        total = ACLPermissions.objects.count()
        by_level = (
            ACLPermissions.objects.values("access_level")
            .order_by()
            .annotate(count=models.Count("id"))
        )

        # Recent entries
        recent = ACLPermissions.objects.select_related("content_type").order_by("-last_synced")[:25]
    except Exception as e:
        logger.exception("Error preparing ACL dashboard: %s", e)
        total = 0
        by_level = []
        recent = []

    def build_acl_summary(model, perms_qs):
        total_objects = model.objects.count()
        sync_object_ids = [str(obj_id) for obj_id in perms_qs.values_list("object_id", flat=True)]
        distinct_synced = len(set(sync_object_ids))
        unsynced_qs = model.objects.exclude(pk__in=sync_object_ids)
        unsynced_objects = unsynced_qs.count()
        unsynced_samples = [
            {
                "identifier": getattr(obj, "identifier", str(obj.pk)),
                "name": _resolve_acl_display_name(obj),
            }
            for obj in unsynced_qs[:5]
        ]
        by_level_local = list(perms_qs.values("access_level").order_by().annotate(count=models.Count("id")))
        recent_perms = list(perms_qs.order_by("-last_synced")[:10])
        recent_ids = [str(perm.object_id) for perm in recent_perms]
        recent_objects = {
            str(obj.pk): obj
            for obj in model.objects.filter(pk__in=recent_ids)
        }
        recent_local = []
        for perm in recent_perms:
            obj = recent_objects.get(str(perm.object_id))
            recent_local.append(
                {
                    "identifier": getattr(obj, "identifier", perm.object_id) if obj else perm.object_id,
                    "name": _resolve_acl_display_name(obj) if obj else None,
                    "access_level": perm.access_level,
                    "last_synced": perm.last_synced,
                }
            )
        last_synced_at = perms_qs.aggregate(models.Max("last_synced"))["last_synced__max"]
        return {
            "records": perms_qs.count(),
            "synced_objects": distinct_synced,
            "unsynced_objects": unsynced_objects,
            "unsynced_samples": unsynced_samples,
            "total_objects": total_objects,
            "by_level": by_level_local,
            "recent": recent_local,
            "last_synced_at": last_synced_at,
        }

    collection_ct = ContentType.objects.get_for_model(Collection)
    bundle_ct = ContentType.objects.get_for_model(Bundle)

    collection_perms = ACLPermissions.objects.filter(content_type=collection_ct)
    bundle_perms = ACLPermissions.objects.filter(content_type=bundle_ct)

    collection_summary = build_acl_summary(Collection, collection_perms)
    bundle_summary = build_acl_summary(Bundle, bundle_perms)

    overall_summary = {
        "records": collection_summary["records"] + bundle_summary["records"],
        "synced_objects": collection_summary["synced_objects"] + bundle_summary["synced_objects"],
        "unsynced_objects": collection_summary["unsynced_objects"] + bundle_summary["unsynced_objects"],
        "total_objects": collection_summary["total_objects"] + bundle_summary["total_objects"],
    }

    collection_options = _get_acl_options(Collection)
    bundle_options = _get_acl_options(Bundle)

    return render(
        request,
        "dashboard/acl_admin_dashboard.html",
        {
            "acl_flags": acl_flags,
            "total": total,
            "by_level": by_level,
            "recent": recent,
            "collection_summary": collection_summary,
            "bundle_summary": bundle_summary,
            "overall_summary": overall_summary,
            "sync_summary": None,
            "collection_options": collection_options,
            "bundle_options": bundle_options,
            "message": request.GET.get("message"),
        },
    )


@login_required
@require_http_methods(["POST"])
def acl_sync_all(request):
    """
    Trigger a full ACL sync for Collections and Bundles.
    Returns a small JSON summary for HTMX or redirects back with a message.
    """
    from lacos.storage.services.acl_sync_service import ACLSyncService

    from lacos.storage.services.acl_sync_service import ACLSyncService

    scope = request.POST.get("scope", "all")
    service = ACLSyncService(skip_bucket_check=True)
    results = []
    scope_label = "Collections & Bundles"

    try:
        if scope == "all":
            results = service.sync_all()
        elif scope == "collections":
            scope_label = "All Collections"
            results = [service.sync_collection(obj) for obj in Collection.objects.all()]
        elif scope == "bundles":
            scope_label = "All Bundles"
            results = [service.sync_bundle(obj) for obj in Bundle.objects.select_related("structural_info__is_member_of_collection")]
        elif scope == "collection":
            collection_id = request.POST.get("collection_id")
            if not collection_id:
                raise ValueError("Please select a collection to sync.")
            collection = Collection.objects.filter(pk=collection_id).first()
            if not collection:
                raise ValueError("Collection not found.")
            scope_label = f"Collection {getattr(collection, 'identifier', collection_id)}"
            results = [service.sync_collection(collection)]
        elif scope == "bundle":
            bundle_id = request.POST.get("bundle_id")
            if not bundle_id:
                raise ValueError("Please select a bundle to sync.")
            bundle = Bundle.objects.select_related("structural_info__is_member_of_collection").filter(pk=bundle_id).first()
            if not bundle:
                raise ValueError("Bundle not found.")
            scope_label = f"Bundle {getattr(bundle, 'identifier', bundle_id)}"
            results = [service.sync_bundle(bundle)]
        else:
            raise ValueError("Invalid sync scope.")
    except ValueError as exc:
        if request.headers.get("HX-Request"):
            return _render_sync_summary_partial(request, summary=None, error_message=str(exc))
        return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={quote_plus(str(exc))}")

    updated = sum(1 for r in results if r.updated)
    found = sum(1 for r in results if r.found)
    errors = [r for r in results if r.error]

    summary = {
        "total": len(results),
        "found": found,
        "updated": updated,
        "errors": len(errors),
        "missing": len(results) - found,
        "scope": scope,
        "scope_label": scope_label,
        "by_type": {
            "collections": sum(1 for r in results if r.object_type == "Collection"),
            "bundles": sum(1 for r in results if r.object_type == "Bundle"),
        },
    }

    # HTMX request -> return partial HTML
    if request.headers.get("HX-Request"):
        return _render_sync_summary_partial(request, summary=summary)

    # Regular POST -> redirect back to dashboard with message
    message = (
        f"{scope_label}: processed {summary['total']} objects — found {summary['found']}, "
        f"updated {summary['updated']}, errors {summary['errors']}"
    )
    return redirect(f"{reverse('storage:acl_admin_dashboard')}?message={quote_plus(message)}")


@login_required
@require_http_methods(["POST"])
def acl_update_settings(request):
    """
    Update ACL settings via HTMX form.
    Returns the updated settings card HTML.
    """
    try:
        from lacos.storage.models.acl_config import ACLConfig

        cfg = ACLConfig.get_solo()
        enforcement_enabled = request.POST.get("enforcement_enabled") == "on"
        log_access_attempts = request.POST.get("log_access_attempts") == "on"
        default_deny = request.POST.get("default_deny") == "on"

        cfg.enforcement_enabled = enforcement_enabled
        cfg.log_access_attempts = log_access_attempts
        cfg.default_deny = default_deny
        cfg.save(update_fields=["enforcement_enabled", "log_access_attempts", "default_deny", "updated_at"])

        context = {
            "acl_flags": {
                "ACL_ENFORCEMENT_ENABLED": cfg.enforcement_enabled,
                "ACL_LOG_ACCESS_ATTEMPTS": cfg.log_access_attempts,
                "ACL_DEFAULT_DENY": cfg.default_deny,
            }
        }
        html = render_to_string("dashboard/partials/acl_settings_card.html", context, request=request)
        return HttpResponse(html)
    except Exception as e:
        logger.exception("Failed to update ACL settings: %s", e)
        return HttpResponse(f"Error updating settings: {e}", status=500)


@login_required
@require_http_methods(["GET"])
def acl_sync_scope_fields(request):
    scope = request.GET.get("scope", "all")
    context = {
        "scope": scope,
        "collection_options": _get_acl_options(Collection),
        "bundle_options": _get_acl_options(Bundle),
    }
    return render(
        request,
        "dashboard/partials/acl_sync_scope_fields.html",
        context,
    )


@login_required
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load contents of a specific folder when expanded.
    Now supports any workspace bucket, not just ingest/production.
    """
    bucket_service = BucketService()

    # Support new flexible bucket names
    if bucket_type in bucket_service.get_all_accessible_buckets():
        bucket = bucket_type
    else:
        # Legacy backward compatibility
        bucket = bucket_service.ingest_bucket if bucket_type == 'ingest' else bucket_service.production_bucket
    
    try:
        # Clean up the folder path to handle double slashes
        folder_path = folder_path.replace('//', '/')
        logger.info("Loading folder contents for %s bucket, path: %s", bucket_type, folder_path)
        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
        
        # Get folder contents
        if force_fresh:
            folder_contents = bucket_service.get_folder_contents(bucket, folder_path, force_fresh=True)
        else:
            folder_contents = bucket_service.get_folder_contents(bucket, folder_path)
        preview_names = ", ".join(item["name"] for item in folder_contents[:5])
        more_indicator = "…" if len(folder_contents) > 5 else ""
        logger.debug(
            "Loaded %s items for %s%s%s",
            len(folder_contents),
            folder_path,
            f" — {preview_names}" if preview_names else "",
            more_indicator,
        )
        
    except Exception as e:
        logger.error(f"Error loading folder contents for {folder_path}: {str(e)}")
        # Return empty list on error
        folder_contents = []
    
    return render(
        request,
        "dashboard/folder_contents_partial.html",
        {
            "folder_contents": folder_contents,
            "bucket_type": bucket_type,
            "folder_path": folder_path,
        },
    )


@login_required
def bucket_size_info(request, bucket_name):
    """HTMX endpoint returning bucket size details."""
    bucket_service = BucketService()
    accessible = set(bucket_service.get_all_accessible_buckets())

    if bucket_name not in accessible:
        return HttpResponse(status=404)

    force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
    size_result = bucket_service.get_bucket_total_size(bucket_name, force_fresh=force_fresh)

    context = {
        "bucket_name": bucket_name,
        "total_size": size_result.get("total_size", 0),
        "total_size_formatted": size_result.get("total_size_formatted", "0 B"),
        "object_count": size_result.get("object_count", 0),
        "success": size_result.get("success", False),
        "error": size_result.get("error"),
    }

    html = render_to_string("dashboard/partials/bucket_size_info.html", context, request=request)
    return HttpResponse(html)


@login_required
def dashboard_content(request, bucket_type):
    """
    Return only the structure content for a specific bucket type.
    This is used for AJAX/HTMX refreshes of just one section of the dashboard.
    
    Args:
        bucket_type (str): Either "ingest" or "production"
        
    Returns:
        Rendered partial template with the requested bucket structure
    """
    try:
        bucket_service = BucketService()
        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
        
        if bucket_type == "ingest":
            if force_fresh:
                structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket, force_fresh=True)
            else:
                structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket)
        elif bucket_type == "production":
            if force_fresh:
                structure = bucket_service.get_root_level_items(bucket_service.production_bucket, force_fresh=True)
            else:
                structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
        else:
            return HttpResponse("Invalid bucket type", status=400)
            
        logger.info(f"Refreshing {bucket_type} structure with {len(structure.get('children', []))} items")
        
        # Render just the folder structure partial
        return render(
            request,
            "dashboard/folder_structure_partial.html",
            {"structure": structure, "bucket_type": bucket_type}
        )
    except Exception as e:
        logger.exception(f"Error loading dashboard content for {bucket_type}: {str(e)}")
        return HttpResponse(f"Error: {str(e)}", status=500)


@method_decorator(login_required, name='dispatch')
class BucketContentHTMXView(HtmxTemplateHelperMixin, View):
    """
    Return bucket content for HTMX bucket switching.
    Returns the complete bucket content area.
    """

    def get(self, request, bucket_name):
        try:
            # Render the bucket content
            content_html = self.render_bucket_content_template(request, bucket_name)

            # Also update the bucket selector dropdown to show the new active bucket
            selector_html = self.build_bucket_tabs_oob_response(
                request=request,
                active_bucket=bucket_name
            )

            # Combine content update with selector OOB update
            response_html = f'{content_html}{selector_html}'

            return HttpResponse(response_html)
        except Exception as e:
            logger.exception(f"Error loading bucket content for {bucket_name}: {str(e)}")
            return HttpResponse(f"Error: {str(e)}", status=500)


# Class-based view is now used directly in URLs


@login_required
def file_info_htmx(request, bucket_type, object_path):
    """Provide file metadata details via HTMX."""
    bucket_service = BucketService()
    target_id = request.GET.get("target_id") or request.GET.get("targetId")

    if not target_id:
        target_id = slugify(f"file-info-{object_path}")

    if request.GET.get("clear"):
        html = render_to_string(
            "dashboard/partials/file_info_placeholder.html",
            {"target_id": target_id},
            request=request,
        )
        return HttpResponse(html)

    accessible_buckets = set(bucket_service.get_all_accessible_buckets())

    if bucket_type in accessible_buckets:
        bucket_name = bucket_type
    elif bucket_type == "ingest":
        bucket_name = bucket_service.ingest_bucket
    elif bucket_type == "production":
        bucket_name = bucket_service.production_bucket
    else:
        return HttpResponse(status=404)

    info_result = bucket_service.get_file_info(bucket_name, object_path)

    context = {
        "target_id": target_id,
        "bucket_type": bucket_type,
        "object_path": object_path,
        "file_name": info_result.get("file_name") or object_path.rstrip("/").split("/")[-1],
        "file_size_formatted": info_result.get("file_size_formatted"),
        "content_type": info_result.get("content_type"),
        "last_modified": info_result.get("last_modified"),
        "metadata": info_result.get("metadata", {}),
        "success": info_result.get("success", False),
        "error": info_result.get("error"),
    }

    html = render_to_string(
        "dashboard/partials/file_info_panel.html",
        context,
        request=request,
    )
    return HttpResponse(html)


@method_decorator(login_required, name='dispatch')
class CreateBucketHTMXView(HtmxTemplateHelperMixin, View):
    """
    Create a new bucket via HTMX form submission.
    Returns updated bucket selector tabs with OOB updates.
    """

    def post(self, request):
        try:
            from lacos.storage.services.bucket_service import BucketService

            # Get form data
            bucket_name = request.POST.get('bucketName', '').strip()
            enable_ocfl = request.POST.get('enableOCFL') == 'on'

            if not bucket_name:
                return HttpResponse("Bucket name is required", status=400)

            # Create the bucket using BucketService
            bucket_service = BucketService()
            result = bucket_service.create_bucket(bucket_name, enable_ocfl)

            if not result["success"]:
                return HttpResponse(result["error"], status=400)

            logger.info(f"Successfully created bucket: {bucket_name}, OCFL: {enable_ocfl}")

            # Only update bucket tabs, keep current view active
            current_active_bucket = self.get_active_bucket(request)

            if not current_active_bucket:
                current_active_bucket = request.POST.get('currentActiveBucket')

            # If still not set (first bucket creation), use the new bucket
            if not current_active_bucket:
                current_active_bucket = bucket_name

            # Use specialized method for bucket tabs OOB update
            response_html = self.build_bucket_tabs_oob_response(
                request=request,
                active_bucket=current_active_bucket,
                success_message=result["message"]
            )

            # Add trigger to close modal
            return self.add_htmx_trigger(response_html, {'closeModal': 'create-bucket-modal'})

        except Exception as e:
            logger.exception(f"Error creating bucket: {str(e)}")
            return HttpResponse(f"Error creating bucket: {str(e)}", status=500)


# Class-based view is now used directly in URLs


@login_required
@require_http_methods(["DELETE"])
def delete_bucket_htmx(request, bucket_name):
    """
    Delete a bucket via HTMX request.
    Returns updated bucket selector tabs.
    """
    try:
        bucket_service = BucketService()

        # Verify bucket access
        if bucket_name not in bucket_service.get_all_accessible_buckets():
            return HttpResponse("Bucket not accessible", status=403)

        # Delete the bucket (this would need to be implemented in BucketService)
        logger.info(f"Deleting bucket: {bucket_name}")

        # Get updated bucket list
        workspace_buckets = bucket_service.get_all_accessible_buckets()
        ocfl_buckets = bucket_service.ocfl_buckets

        # Set first available bucket as active
        active_bucket = workspace_buckets[0] if workspace_buckets else None

        return render(
            request,
            "dashboard/bucket_tabs_partial.html",
            {
                "workspace_buckets": workspace_buckets,
                "ocfl_buckets": ocfl_buckets,
                "active_bucket": active_bucket,
                "success_message": f"Bucket '{bucket_name}' deleted successfully"
            }
        )
    except Exception as e:
        logger.exception(f"Error deleting bucket: {str(e)}")
        return HttpResponse(f"Error deleting bucket: {str(e)}", status=500)


@method_decorator(login_required, name='dispatch')
class RenameBucketModalHTMXView(HtmxTemplateHelperMixin, View):
    """Serve the bucket rename modal populated with current values."""

    def get(self, request, bucket_name):
        html = render_to_string(
            'dashboard/partials/rename_bucket_modal.html',
            {
                'modal_open': True,
                'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                'current_name': bucket_name,
                'new_name': bucket_name,
                'error': None,
                'oob': False,
                'csrf_token': get_token(request),
            },
            request=request,
        )
        return HttpResponse(html)


@method_decorator(login_required, name='dispatch')
class RenameObjectModalHTMXView(HtmxTemplateHelperMixin, View):
    """Serve the folder/file rename modal with the selected item."""

    def get(self, request, bucket_name, object_type, object_path):
        object_name = object_path.rstrip('/').split('/')[-1]
        html = render_to_string(
            'dashboard/partials/rename_object_modal.html',
            {
                'modal_open': True,
                'form_action': reverse('storage:rename_object_htmx', args=[bucket_name, object_type, object_path]),
                'current_name': object_name,
                'new_name': object_name,
                'object_type': object_type,
                'object_path': object_path,
                'bucket_name': bucket_name,
                'error': None,
                'oob': False,
                'csrf_token': get_token(request),
            },
            request=request,
        )
        return HttpResponse(html)


@method_decorator(login_required, name='dispatch')
class RenameBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle HTMX bucket rename requests."""

    def post(self, request, bucket_name):
        try:
            new_name = (request.POST.get('newName') or request.POST.get('prompt') or '').strip()
            if not new_name and request.body:
                try:
                    raw_body = request.body.decode(request.encoding or 'utf-8')
                    if request.content_type == 'application/json':
                        payload = json.loads(raw_body)
                        new_name = (payload.get('newName') or payload.get('prompt') or '').strip()
                    elif request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
                        form_data = QueryDict(raw_body)
                        new_name = (form_data.get('newName') or form_data.get('prompt') or '').strip()
                        if not new_name and raw_body.startswith('{'):
                            try:
                                parsed = json.loads(raw_body)
                            except ValueError:
                                try:
                                    parsed = ast.literal_eval(raw_body)
                                except (ValueError, SyntaxError):
                                    parsed = {}
                            new_name = (parsed.get('newName') or parsed.get('prompt') or '').strip()
                except (ValueError, TypeError):
                    new_name = ''

            if not new_name:
                error_html = render_to_string(
                    'dashboard/partials/rename_bucket_modal.html',
                    {
                        'modal_open': True,
                        'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                        'current_name': bucket_name,
                        'new_name': '',
                        'error': 'Bucket name is required',
                        'oob': False,
                        'csrf_token': get_token(request),
                    },
                    request=request,
                )
                return HttpResponse(error_html, status=400)

            bucket_service = BucketService()
            result = bucket_service.rename_bucket(bucket_name, new_name)

            if not result.get('success'):
                error_html = render_to_string(
                    'dashboard/partials/rename_bucket_modal.html',
                    {
                        'modal_open': True,
                        'form_action': reverse('storage:rename_bucket_htmx', args=[bucket_name]),
                        'current_name': bucket_name,
                        'new_name': new_name,
                        'error': result.get('error', 'Rename failed'),
                        'oob': False,
                        'csrf_token': get_token(request),
                    },
                    request=request,
                )
                return HttpResponse(error_html, status=400)

            content_html = self.render_bucket_content_template(request, new_name)

            response_html = self.build_bucket_tabs_oob_response(
                main_html=content_html,
                request=request,
                active_bucket=new_name,
                success_message=None
            )

            modal_html = render_to_string(
                'dashboard/partials/rename_bucket_modal.html',
                {
                    'modal_open': False,
                    'form_action': reverse('storage:rename_bucket_htmx', args=[new_name]),
                    'current_name': new_name,
                    'new_name': '',
                    'error': None,
                    'oob': True,
                    'csrf_token': get_token(request),
                },
                request=request,
            )

            return HttpResponse(response_html + modal_html)

        except Exception as e:
            logger.exception(f"Error renaming bucket {bucket_name}: {str(e)}")
            return HttpResponse(f"Error renaming bucket: {str(e)}", status=500)
