"""
Archivist dashboard views.

Handles the main archivist dashboard, bucket content display,
and folder navigation for storage management.
"""
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from lacos.common.mixins import BucketCoordinatorMixin
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.observability import profiling_scope

logger = logging.getLogger(__name__)


@login_required
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


@login_required
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

        # Get bucket name from session
        bucket_state = BucketCoordinatorMixin()
        bucket_name = bucket_state.get_active_bucket(request)

        if not bucket_name:
            return render(
                request,
                "dashboard/partials/folder_contents_error.html",
                {"error": "No active bucket selected"},
            )

        session.metadata["bucket_name"] = bucket_name

        try:
            # Get folder contents
            contents = bucket_service.get_folder_contents(bucket_name, folder_path)
            session.metadata["items_loaded"] = len(contents)

            return render(
                request,
                "dashboard/folder_contents_partial.html",
                {
                    "items": contents,
                    "folder_path": folder_path,
                    "bucket_name": bucket_name,
                },
            )
        except Exception as e:
            logger.error(f"Error loading folder contents for {folder_path}: {str(e)}")
            session.metadata["error"] = str(e)
            return render(
                request,
                "dashboard/partials/folder_contents_error.html",
                {"error": f"Failed to load folder contents: {str(e)}"},
            )


@login_required
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

        if bucket_type not in workspace_buckets:
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Bucket '{bucket_type}' not found"},
            )

        # Set active bucket in session
        bucket_state.set_active_bucket(request, bucket_type)
        session.metadata["bucket_type"] = bucket_type

        force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

        try:
            # Get root level items
            root_data = bucket_service.get_root_level_items(bucket_type, force_fresh=force_fresh)
            children = root_data.get("children", [])

            session.metadata["items_loaded"] = len(children)

            return render(
                request,
                "dashboard/bucket_content_partial.html",
                {
                    "bucket_name": bucket_type,
                    "items": children,
                    "force_fresh": force_fresh,
                },
            )
        except Exception as e:
            logger.error(f"Error loading dashboard content for {bucket_type}: {str(e)}")
            session.metadata["error"] = str(e)
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Failed to load bucket contents: {str(e)}"},
            )


@login_required
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
            logger.error(f"Error getting bucket size for {bucket_name}: {str(e)}")
            session.metadata["error"] = str(e)
            return render(
                request,
                "dashboard/partials/error.html",
                {"error": f"Failed to get bucket size: {str(e)}"},
            )
