"""
Archivist dashboard views.

Handles the main archivist dashboard, bucket content display,
and folder navigation for storage management.
"""
import logging
from urllib.parse import unquote
from django.shortcuts import render
from django.urls import reverse

from lacos.common.mixins import BucketCoordinatorMixin
from lacos.common.mixins.htmx_template_helpers import ROOT_FOLDER_SENTINEL
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.observability import profiling_scope
from lacos.storage.permissions import manager_or_archivist_required

logger = logging.getLogger(__name__)


@manager_or_archivist_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing all workspace buckets.
    Only loads root level items initially for better performance.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "archivist_dashboard",
        request_id=request_id,
        metadata={
            "htmx": bool(request.headers.get("HX-Request")),
            "force_fresh": request.GET.get("force_fresh", "false").lower() == "true",
        },
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)
        bucket_state = BucketCoordinatorMixin()

        workspace_buckets = bucket_service.get_all_accessible_buckets()
        session.metadata["workspace_bucket_count"] = len(workspace_buckets)

        active_bucket = bucket_state.ensure_active_bucket(request, workspace_buckets)
        session.metadata["active_bucket"] = active_bucket

        auto_load_url = None
        if active_bucket:
            auto_load_url = reverse("storage:bucket_content_htmx", kwargs={"bucket_name": active_bucket})
            if request.GET.get("force_fresh", "false").lower() == "true":
                auto_load_url = f"{auto_load_url}?force_fresh=true"

        message = request.GET.get('message', None)

        return render(
            request,
            "dashboard/archivist_dashboard.html",
            {
                "workspace_buckets": workspace_buckets,
                "active_bucket": active_bucket,
                "ocfl_buckets": bucket_service.ocfl_buckets,
                "message": message,
                "auto_load_url": auto_load_url,
            },
        )


@manager_or_archivist_required
def load_folder_contents(request, bucket_type, folder_path):
    """
    Load folder contents via HTMX for lazy expansion.

    This view is called when a folder is clicked to load its contents
    without reloading the entire page.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "load_folder_contents",
        request_id=request_id,
        metadata={
            "bucket_type": bucket_type,
            "folder_path": folder_path,
            "htmx": bool(request.headers.get("HX-Request")),
        },
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)

        workspace_buckets = set(bucket_service.get_all_accessible_buckets())
        if bucket_type in workspace_buckets:
            bucket_name = bucket_type
        elif bucket_type == "ingest":
            bucket_name = bucket_service.ingest_bucket
        elif bucket_type == "production":
            bucket_name = bucket_service.production_bucket
        else:
            bucket_name = bucket_type

        session.metadata["bucket_name"] = bucket_name
        session.metadata["resolved_bucket"] = bucket_name

        try:
            sanitized_path = ROOT_FOLDER_SENTINEL if folder_path == ROOT_FOLDER_SENTINEL else folder_path
            if sanitized_path == ROOT_FOLDER_SENTINEL:
                sanitized_path = ""
            sanitized_path = sanitized_path.replace("//", "/")

            force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
            session.metadata["force_fresh"] = force_fresh

            try:
                requested_max_keys = int(request.GET.get("max_keys", "") or 0)
            except ValueError:
                requested_max_keys = 0
            pagination_enabled = getattr(bucket_service, "dashboard_pagination_enabled", True)
            if requested_max_keys <= 0:
                requested_max_keys = bucket_service.dashboard_page_size if pagination_enabled else 0
            continuation_token = request.GET.get("continuation_token") or None

            session.metadata["max_keys"] = requested_max_keys
            session.metadata["continuation_token"] = continuation_token

            # Get folder contents. Some S3-compatible backends may return continuation tokens
            # that need one extra decoding pass when routed through query params.
            try:
                contents = bucket_service.get_folder_contents(
                    bucket_name,
                    sanitized_path,
                    max_keys=requested_max_keys if pagination_enabled else None,
                    continuation_token=continuation_token,
                    force_fresh=force_fresh,
                    raise_errors=True,
                )
            except Exception:
                decoded_token = unquote(continuation_token) if continuation_token else None
                if continuation_token and decoded_token and decoded_token != continuation_token:
                    logger.warning(
                        "Retrying folder pagination with decoded continuation token for %s",
                        sanitized_path or ROOT_FOLDER_SENTINEL,
                    )
                    session.metadata["continuation_token_retry"] = True
                    contents = bucket_service.get_folder_contents(
                        bucket_name,
                        sanitized_path,
                        max_keys=requested_max_keys if pagination_enabled else None,
                        continuation_token=decoded_token,
                        force_fresh=force_fresh,
                        raise_errors=True,
                    )
                else:
                    raise
            session.metadata["items_loaded"] = len(contents)
            session.metadata["has_more"] = contents.has_more
            session.metadata["next_token"] = contents.next_token

            session.metadata["items_loaded"] = len(contents)

            return render(
                request,
                "dashboard/folder_contents_partial.html",
                {
                    "listing": contents,
                    "folder_path": sanitized_path,
                    "folder_path_param": sanitized_path or ROOT_FOLDER_SENTINEL,
                    "bucket_type": bucket_type,
                    "max_keys": requested_max_keys,
                    "is_root": sanitized_path in ("", None),
                    "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
                },
            )
        except Exception as e:
            logger.error("Error loading folder contents", extra={"folder_path": folder_path, "error": str(e)})
            session.metadata["error"] = str(e)

            requested_max_keys = locals().get("requested_max_keys", 0)
            continuation_token = locals().get("continuation_token", None)
            sanitized_path = locals().get("sanitized_path", folder_path)
            if sanitized_path == ROOT_FOLDER_SENTINEL:
                sanitized_path = ""

            return render(
                request,
                "dashboard/partials/folder_contents_error.html",
                {"error": f"Failed to load folder contents: {str(e)}"},
            )


@manager_or_archivist_required
def dashboard_content(request, bucket_type):
    """
    Load the main content area of the dashboard for a specific bucket.

    Used when switching between buckets via HTMX.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "dashboard_content",
        request_id=request_id,
        metadata={
            "bucket_type": bucket_type,
            "htmx": bool(request.headers.get("HX-Request")),
        },
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)
        bucket_state = BucketCoordinatorMixin()

        workspace_buckets = bucket_service.get_all_accessible_buckets()
        pagination_enabled = getattr(bucket_service, "dashboard_pagination_enabled", True)
        page_size = bucket_service.dashboard_page_size if pagination_enabled else None

        if bucket_type in workspace_buckets:
            resolved_bucket = bucket_type
        elif bucket_type == "ingest":
            resolved_bucket = bucket_service.ingest_bucket
        elif bucket_type == "production":
            resolved_bucket = bucket_service.production_bucket
        else:
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Bucket '{bucket_type}' not found"},
            )

        if resolved_bucket not in workspace_buckets:
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Bucket '{bucket_type}' not found"},
            )

        # Set active bucket in session
        bucket_state.set_active_bucket(request, resolved_bucket)
        session.metadata["bucket_type"] = bucket_type
        session.metadata["resolved_bucket"] = resolved_bucket
        session.metadata["page_size"] = page_size

        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

        try:
            listing = bucket_service.get_folder_contents(
                resolved_bucket,
                "",
                max_keys=page_size if pagination_enabled else None,
                force_fresh=force_fresh,
            )

            session.metadata["items_loaded"] = len(listing)
            session.metadata["has_more"] = listing.has_more
            session.metadata["next_token"] = listing.next_token

            return render(
                request,
                "dashboard/bucket_content_partial.html",
                {
                    "bucket_name": resolved_bucket,
                    "listing": listing,
                    "force_fresh": force_fresh,
                    "page_size": page_size,
                    "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
                },
            )
        except Exception as e:
            logger.error("Error loading dashboard content", extra={"bucket_type": bucket_type, "error": str(e)})
            session.metadata["error"] = str(e)
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Failed to load bucket contents: {str(e)}"},
            )


@manager_or_archivist_required
def bucket_size_info(request, bucket_name):
    """
    Get bucket size information for display in the dashboard.

    Returns formatted size and object count.
    """
    request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
    with profiling_scope(
        "bucket_size_info",
        request_id=request_id,
        metadata={"bucket_name": bucket_name},
    ) as session:
        bucket_service = BucketService(skip_bucket_check=True)

        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

        try:
            size_info = bucket_service.get_bucket_total_size(bucket_name, force_fresh=force_fresh)
            session.metadata["total_size"] = size_info.get("total_size", 0)
            session.metadata["object_count"] = size_info.get("object_count", 0)

            return render(
                request,
                "dashboard/partials/bucket_size_info.html",
                {
                    "bucket_name": bucket_name,
                    "total_size": size_info.get("total_size", 0),
                    "total_size_formatted": size_info.get("total_size_formatted", "0 B"),
                    "object_count": size_info.get("object_count", 0),
                    "success": size_info.get("success", False),
                    "error": size_info.get("error"),
                },
            )
        except Exception as e:
            logger.error("Error getting bucket size", extra={"bucket_name": bucket_name, "error": str(e)})
            session.metadata["error"] = str(e)
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Failed to get bucket size: {str(e)}"},
            )
