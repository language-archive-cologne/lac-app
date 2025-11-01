import ast
import json
import logging
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse, JsonResponse, QueryDict
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views import View
from django.views.decorators.http import require_http_methods

from lacos.common.mixins import BucketCoordinatorMixin, HtmxTemplateHelperMixin
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing all workspace buckets.
    Only loads root level items initially for better performance.
    """
    logger.info("=" * 80)
    logger.info("STORAGE DASHBOARD ACCESS")
    logger.info("User: %s, Force Fresh: %s", request.user.username, request.GET.get("force_fresh", "false"))
    logger.info("=" * 80)

    try:
        # Initialize service
        logger.info("Initializing BucketService...")
        bucket_service = BucketService()
        logger.info("✅ BucketService initialized")

        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

        logger.info("Fetching accessible buckets...")
        handshake_start = time.time()

        try:
            workspace_buckets = bucket_service.get_all_accessible_buckets(
                force_refresh=force_fresh,
                raise_on_error=True,
            )
            handshake_elapsed = time.time() - handshake_start
            metadata = bucket_service.bucket_cache_metadata
            source = metadata.get("source")

            if source == "cache":
                logger.info(
                    "Buckets served from cache (expires in %.2fs)",
                    metadata.get("expires_in", 0.0) or 0.0,
                )
            else:
                logger.info("Testing S3 connection handshake...")
                logger.info("Endpoint: %s", bucket_service.endpoint_url)
                logger.info("Region: %s", bucket_service.region)
                logger.info("✅ S3 connection successful (%.2fs)", handshake_elapsed)
                if metadata.get("duration") is not None:
                    logger.info("Bucket listing duration: %.2fs", metadata["duration"])

            logger.info("Buckets visible: %d", len(workspace_buckets))
            if workspace_buckets:
                logger.info("Bucket names: %s", workspace_buckets[:10])

        except Exception as e:
            handshake_elapsed = time.time() - handshake_start
            logger.error("❌ S3 connection failed after %.2fs", handshake_elapsed)
            logger.error("Error type: %s", type(e).__name__)
            logger.error("Error message: %s", str(e))

            if "timeout" in str(e).lower():
                logger.error("→ Connection timeout - check network/firewall")
            elif "connection" in str(e).lower():
                logger.error("→ Connection refused/failed - check endpoint URL and network")
            elif "ssl" in str(e).lower() or "certificate" in str(e).lower():
                logger.error("→ SSL/TLS issue - check certificates")
            elif "credentials" in str(e).lower() or "forbidden" in str(e).lower():
                logger.error("→ Authentication issue - check access keys")

            raise

        bucket_state = BucketCoordinatorMixin()

        active_bucket = bucket_state.ensure_active_bucket(request, workspace_buckets)
        logger.info("Active bucket: %s", active_bucket or "None")

        auto_load_url = None
        if active_bucket:
            auto_load_url = reverse("storage:bucket_content_htmx", kwargs={"bucket_name": active_bucket})
            if force_fresh:
                auto_load_url = f"{auto_load_url}?force_fresh=true"
            logger.info("Auto-load URL: %s", auto_load_url)

        # Check for success message
        message = request.GET.get('message', None)

        logger.info("✅ Dashboard render complete")
        logger.info("=" * 80)

        return render(
            request,
            "dashboard/archivist_dashboard.html",
            {
                "workspace_buckets": workspace_buckets,
                "active_bucket": active_bucket,
                "auto_load_url": auto_load_url,
                "ocfl_buckets": bucket_service.ocfl_buckets,
                "message": message,
            },
        )
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ DASHBOARD ERROR")
        logger.exception("Error rendering dashboard: %s", str(e))
        logger.error("=" * 80)
        raise


@login_required
def acl_admin_dashboard(request):
    """
    Render the ACL Admin Dashboard with current settings, summary stats,
    and recent permission records.
    """
    # Settings flags (DB-backed with settings fallback)
    from lacos.storage.models.acl_config import ACLConfig
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
        recent = (
            ACLPermissions.objects.select_related("content_type")
            .order_by("-last_synced")[:25]
        )
    except Exception as e:
        logger.exception("Error preparing ACL dashboard: %s", e)
        total = 0
        by_level = []
        recent = []

    return render(
        request,
        "dashboard/acl_admin_dashboard.html",
        {
            "acl_flags": acl_flags,
            "total": total,
            "by_level": by_level,
            "recent": recent,
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

    service = ACLSyncService(skip_bucket_check=True)
    results = service.sync_all()

    updated = sum(1 for r in results if r.updated)
    found = sum(1 for r in results if r.found)
    errors = [r for r in results if r.error]

    summary = {
        "total": len(results),
        "found": found,
        "updated": updated,
        "errors": len(errors),
    }

    # HTMX request -> return partial JSON
    if request.headers.get("HX-Request"):
        return JsonResponse({"success": True, "summary": summary})

    # Regular POST -> redirect back to dashboard with message
    message = (
        f"Synced {summary['total']} objects — found {summary['found']}, updated {summary['updated']}, "
        f"errors {summary['errors']}"
    )
    # Fall back to rendering dashboard with message
    return render(
        request,
        "dashboard/acl_admin_dashboard.html",
        {"message": message, "acl_flags": {}, "total": 0, "by_level": [], "recent": []},
        status=200,
    )


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
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load contents of a specific folder when expanded.
    Now supports any workspace bucket, not just ingest/production.
    Supports pagination via continuation_token parameter.
    """
    bucket_service = BucketService()
    force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

    # Support new flexible bucket names
    if bucket_type in bucket_service.get_all_accessible_buckets(force_refresh=force_fresh):
        bucket = bucket_type
    else:
        # Legacy backward compatibility
        legacy_map = {
            'ingest': bucket_service.ingest_bucket,
            'production': bucket_service.production_bucket,
        }
        bucket = legacy_map.get(bucket_type)

    if not bucket:
        logger.warning("Requested bucket '%s' could not be resolved", bucket_type)
        return HttpResponse(status=404)

    try:
        # Clean up the folder path to handle double slashes
        folder_path = folder_path.replace('//', '/')
        logger.info("Loading folder contents for %s bucket, path: %s", bucket_type, folder_path)
        continuation_token = request.GET.get("continuation_token")

        # Get folder contents
        folder_result = bucket_service.get_folder_contents(
            bucket,
            folder_path,
            force_fresh=force_fresh,
            continuation_token=continuation_token,
        )

        folder_contents = folder_result.get("items", [])
        has_more = folder_result.get("has_more", False)
        next_token = folder_result.get("next_token")

        preview_names = ", ".join(item["name"] for item in folder_contents[:5])
        more_indicator = "…" if len(folder_contents) > 5 else ""
        logger.debug(
            "Loaded %s items for %s%s%s (has_more=%s)",
            len(folder_contents),
            folder_path,
            f" — {preview_names}" if preview_names else "",
            more_indicator,
            has_more,
        )

    except Exception as e:
        logger.error(f"Error loading folder contents for {folder_path}: {str(e)}")
        # Return empty list on error
        folder_contents = []
        has_more = False
        next_token = None

    return render(
        request,
        "dashboard/folder_contents_partial.html",
        {
            "folder_contents": folder_contents,
            "bucket_type": bucket_type,
            "folder_path": folder_path,
            "has_more": has_more,
            "next_token": next_token,
        },
    )


@login_required
def bucket_size_info(request, bucket_name):
    """HTMX endpoint returning bucket size details."""
    bucket_service = BucketService()
    force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
    accessible = set(bucket_service.get_all_accessible_buckets(force_refresh=force_fresh))

    if bucket_name not in accessible:
        return HttpResponse(status=404)

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
    """Return the structure content for a specific bucket via HTMX refresh."""
    try:
        bucket_service = BucketService()
        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
        continuation_token = request.GET.get("continuation_token")

        accessible = set(bucket_service.get_all_accessible_buckets(force_refresh=force_fresh))
        bucket_name = bucket_type if bucket_type in accessible else None
        if not bucket_name:
            legacy_map = {
                "ingest": bucket_service.ingest_bucket,
                "production": bucket_service.production_bucket,
            }
            bucket_name = legacy_map.get(bucket_type)

        if not bucket_name:
            return HttpResponse("Invalid bucket type", status=400)

        structure = bucket_service.get_root_level_items(
            bucket_name,
            force_fresh=force_fresh,
            continuation_token=continuation_token,
        )

        logger.info(
            "Refreshing %s structure with %s items (force_fresh=%s, has_more=%s)",
            bucket_name,
            len(structure.get('children', [])),
            force_fresh,
            structure.get('has_more', False),
        )

        # Render just the folder structure partial
        return render(
            request,
            "dashboard/folder_structure_partial.html",
            {"structure": structure, "bucket_type": bucket_name}
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
        logger.info("=" * 80)
        logger.info("BUCKET CONTENT LOAD: %s", bucket_name)
        logger.info("User: %s, HTMX Request: %s", request.user.username, request.headers.get('HX-Request', 'No'))
        logger.info("=" * 80)

        try:
            logger.info("Rendering bucket content template for: %s", bucket_name)

            # Render the bucket content
            content_html = self.render_bucket_content_template(request, bucket_name)
            logger.info("✅ Content template rendered (%d chars)", len(content_html))

            # Also update the bucket selector dropdown to show the new active bucket
            logger.info("Building bucket tabs OOB response")
            selector_html = self.build_bucket_tabs_oob_response(
                request=request,
                active_bucket=bucket_name
            )
            logger.info("✅ Bucket tabs OOB rendered (%d chars)", len(selector_html))

            # Combine content update with selector OOB update
            response_html = f'{content_html}{selector_html}'

            logger.info("✅ Bucket content load complete (total: %d chars)", len(response_html))
            logger.info("=" * 80)

            return HttpResponse(response_html)
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ BUCKET CONTENT ERROR: %s", bucket_name)
            logger.exception("Error loading bucket content: %s", str(e))
            logger.error("=" * 80)
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
    else:
        legacy_map = {
            "ingest": bucket_service.ingest_bucket,
            "production": bucket_service.production_bucket,
        }
        bucket_name = legacy_map.get(bucket_type)

    if not bucket_name:
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
