"""
HTMX handlers for bucket operations.

Handles bucket content loading, creation, deletion, and rename modals.
"""
import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

from lacos.common.mixins import BucketCoordinatorMixin, HtmxTemplateHelperMixin
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.observability import profiling_scope

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class BucketContentHTMXView(HtmxTemplateHelperMixin, View):
    """
    Handle HTMX requests for bucket content display.
    """

    def get(self, request, bucket_name):
        """Load and display bucket contents via HTMX."""
        request_id = request.headers.get("X-Request-ID") or request.headers.get("HX-Request")
        with profiling_scope(
            "bucket_content_htmx",
            request_id=request_id,
            metadata={"bucket_name": bucket_name},
        ) as session:
            bucket_service = BucketService(skip_bucket_check=True)
            bucket_state = BucketCoordinatorMixin()

            # Set as active bucket
            bucket_state.set_active_bucket(request, bucket_name)

            force_fresh = request.GET.get("force_fresh", "false").lower() == "true"

            try:
                # Get root level items
                root_data = bucket_service.get_root_level_items(bucket_name, force_fresh=force_fresh)
                children = root_data.get("children", [])

                session.metadata["items_loaded"] = len(children)

                return render(
                    request,
                    "dashboard/bucket_content_partial.html",
                    {
                        "bucket_name": bucket_name,
                        "items": children,
                        "force_fresh": force_fresh,
                    },
                )
            except Exception as e:
                logger.error(f"Error loading bucket content for {bucket_name}: {str(e)}")
                session.metadata["error"] = str(e)
                return self.htmx_error_response(f"Failed to load bucket: {str(e)}")


@method_decorator(login_required, name="dispatch")
class CreateBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle bucket creation via HTMX."""

    def post(self, request):
        """Create a new bucket."""
        bucket_name = request.POST.get("bucket_name", "").strip()
        enable_ocfl = request.POST.get("enable_ocfl") == "on"

        if not bucket_name:
            return self.htmx_error_response("Bucket name is required")

        bucket_service = BucketService(skip_bucket_check=True)

        try:
            result = bucket_service.create_bucket(bucket_name, enable_ocfl=enable_ocfl)

            if result.get("success"):
                # Return updated bucket list
                workspace_buckets = bucket_service.get_all_accessible_buckets()
                return render(
                    request,
                    "dashboard/partials/bucket_list.html",
                    {"workspace_buckets": workspace_buckets, "active_bucket": bucket_name},
                )
            else:
                return self.htmx_error_response(result.get("error", "Failed to create bucket"))

        except Exception as e:
            logger.error(f"Error creating bucket {bucket_name}: {str(e)}")
            return self.htmx_error_response(str(e))


@login_required
@require_http_methods(["POST"])
def delete_bucket_htmx(request, bucket_name):
    """Delete a bucket via HTMX."""
    bucket_service = BucketService(skip_bucket_check=True)

    try:
        result = bucket_service.delete_bucket(bucket_name)

        if result.get("success"):
            # Return updated bucket list
            workspace_buckets = bucket_service.get_all_accessible_buckets()
            active_bucket = workspace_buckets[0] if workspace_buckets else None

            # Update session
            bucket_state = BucketCoordinatorMixin()
            bucket_state.set_active_bucket(request, active_bucket)

            return render(
                request,
                "dashboard/partials/bucket_list.html",
                {"workspace_buckets": workspace_buckets, "active_bucket": active_bucket},
            )
        else:
            html = render_to_string(
                "dashboard/partials/error.html",
                {"error": result.get("error", "Failed to delete bucket")},
                request=request,
            )
            return HttpResponse(html, status=400)

    except Exception as e:
        logger.error(f"Error deleting bucket {bucket_name}: {str(e)}")
        html = render_to_string(
            "dashboard/partials/error.html",
            {"error": str(e)},
            request=request,
        )
        return HttpResponse(html, status=500)


@method_decorator(login_required, name="dispatch")
class RenameBucketModalHTMXView(HtmxTemplateHelperMixin, View):
    """Display rename bucket modal."""

    def get(self, request, bucket_name):
        """Render the rename bucket modal."""
        return render(
            request,
            "dashboard/modals/rename_bucket_modal.html",
            {"bucket_name": bucket_name},
        )


@method_decorator(login_required, name="dispatch")
class RenameObjectModalHTMXView(HtmxTemplateHelperMixin, View):
    """Display rename object (folder/file) modal."""

    def get(self, request, bucket_name, object_type, object_path):
        """Render the rename object modal."""
        return render(
            request,
            "dashboard/modals/rename_object_modal.html",
            {
                "bucket_name": bucket_name,
                "object_type": object_type,
                "object_path": object_path,
            },
        )


@method_decorator(login_required, name="dispatch")
class RenameBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle bucket rename via HTMX."""

    def post(self, request, bucket_name):
        """Rename a bucket."""
        new_name = request.POST.get("new_name", "").strip()

        if not new_name:
            return self.htmx_error_response("New bucket name is required")

        bucket_service = BucketService(skip_bucket_check=True)

        try:
            result = bucket_service.rename_bucket(bucket_name, new_name)

            if result.get("success"):
                # Return updated bucket list
                workspace_buckets = bucket_service.get_all_accessible_buckets()

                # Update active bucket
                bucket_state = BucketCoordinatorMixin()
                bucket_state.set_active_bucket(request, new_name)

                return render(
                    request,
                    "dashboard/partials/bucket_list.html",
                    {"workspace_buckets": workspace_buckets, "active_bucket": new_name},
                )
            else:
                return self.htmx_error_response(result.get("error", "Failed to rename bucket"))

        except Exception as e:
            logger.error(f"Error renaming bucket {bucket_name} to {new_name}: {str(e)}")
            return self.htmx_error_response(str(e))


@login_required
def file_info_htmx(request, bucket_type, object_path):
    """
    Get file information for display.

    Used to show file details in a modal or sidebar.
    """
    bucket_service = BucketService(skip_bucket_check=True)

    try:
        file_info = bucket_service.get_file_info(bucket_type, object_path)

        return render(
            request,
            "dashboard/partials/file_info.html",
            {
                "bucket_name": bucket_type,
                "file_info": file_info,
                "object_path": object_path,
            },
        )
    except Exception as e:
        logger.error(f"Error getting file info for {object_path}: {str(e)}")
        html = render_to_string(
            "dashboard/partials/error.html",
            {"error": f"Failed to load file info: {str(e)}"},
            request=request,
        )
        return HttpResponse(html, status=500)
