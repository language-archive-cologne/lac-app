"""
HTMX handlers for bucket operations.

Handles bucket content loading, creation, deletion, and rename modals.
"""
import logging
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

from lacos.common.mixins import BucketCoordinatorMixin, HtmxTemplateHelperMixin
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.observability import profiling_scope
from lacos.storage.permissions import archivist_required

logger = logging.getLogger(__name__)


@method_decorator(archivist_required, name="dispatch")
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
            try:
                force_fresh = request.GET.get("force_fresh", "false").lower() == "true"
                continuation_token = request.GET.get("continuation_token") or None
                try:
                    requested_max_keys = int(request.GET.get("max_keys", "") or 0)
                except ValueError:
                    requested_max_keys = 0

                # Determine prefetch behavior - default True for initial loads
                # Only defer loading when explicitly paginating or requested
                prefetch_root = True
                prefetch_param = request.GET.get("prefetch_root")
                if prefetch_param is not None:
                    prefetch_root = prefetch_param.lower() == "true"

                session.metadata.update({
                    "force_fresh": force_fresh,
                    "prefetch_root": prefetch_root,
                })

                # Use the mixin method which provides correct template context
                content_html = self.render_bucket_content_template(
                    request,
                    bucket_name,
                    continuation_token=continuation_token,
                    max_keys=requested_max_keys if requested_max_keys > 0 else None,
                    force_fresh=force_fresh,
                    prefetch_root=prefetch_root,
                )
                selector_html = self.build_bucket_tabs_oob_response(
                    request=request,
                    active_bucket=bucket_name
                )
                session.metadata["rendered"] = True

                return HttpResponse(f'{content_html}{selector_html}')
            except Exception as e:
                logger.error(f"Error loading bucket content for {bucket_name}: {str(e)}")
                session.metadata["error"] = str(e)
                return self.htmx_error_response(f"Failed to load bucket: {str(e)}")


@method_decorator(archivist_required, name="dispatch")
class CreateBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle bucket creation via HTMX."""

    def post(self, request):
        """Create a new bucket."""
        bucket_name = request.POST.get("bucketName", "").strip()
        enable_ocfl = request.POST.get("enableOCFL") == "on"

        if not bucket_name:
            return self.htmx_error_response("Bucket name is required")

        bucket_service = BucketService(skip_bucket_check=True)

        try:
            result = bucket_service.create_bucket(bucket_name, enable_ocfl=enable_ocfl)

            if result.get("success"):
                # Set new bucket as active and build OOB response
                self.set_active_bucket(request, bucket_name)

                # Render bucket content for the new bucket
                content_html = self.render_bucket_content_template(request, bucket_name)

                # Build response with OOB bucket tabs update
                response_html = self.build_bucket_tabs_oob_response(
                    main_html=content_html,
                    request=request,
                    active_bucket=bucket_name,
                    success_message=f"Bucket '{bucket_name}' created successfully",
                )

                # Add OOB update for upload modal bucket select
                bucket_select_html = self.render_bucket_select_template(
                    request, active_bucket=bucket_name, oob=True
                )
                logger.info(f"Bucket select OOB HTML: {bucket_select_html[:200]}...")
                response_html = f"{response_html}{bucket_select_html}"

                # Return response with trigger to close modal
                return self.add_htmx_trigger(
                    response_html,
                    {"closeModal": "create-bucket-modal"},
                )
            else:
                return self.htmx_error_response(result.get("error", "Failed to create bucket"))

        except Exception as e:
            logger.error(f"Error creating bucket {bucket_name}: {str(e)}")
            return self.htmx_error_response(str(e))


@archivist_required
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


@method_decorator(archivist_required, name="dispatch")
class RenameBucketModalHTMXView(HtmxTemplateHelperMixin, View):
    """Display rename bucket modal."""

    def get(self, request, bucket_name):
        """Render the rename bucket modal."""
        return render(
            request,
            "dashboard/partials/rename_bucket_modal.html",
            {"bucket_name": bucket_name},
        )


@method_decorator(archivist_required, name="dispatch")
class RenameObjectModalHTMXView(HtmxTemplateHelperMixin, View):
    """Display rename object (folder/file) modal."""

    def get(self, request, bucket_name, object_type, object_path):
        """Render the rename object modal."""
        from django.urls import reverse

        # Extract the current name from the object path
        current_name = object_path.rstrip('/').rsplit('/', 1)[-1]

        # Build the form action URL
        form_action = reverse(
            'storage:rename_object_htmx',
            kwargs={
                'bucket_name': bucket_name,
                'object_type': object_type,
                'object_path': object_path,
            }
        )

        return render(
            request,
            "dashboard/partials/rename_object_modal.html",
            {
                "bucket_name": bucket_name,
                "object_type": object_type,
                "object_path": object_path,
                "current_name": current_name,
                "form_action": form_action,
                "modal_open": True,
                "oob": True,
            },
        )


@method_decorator(archivist_required, name="dispatch")
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


@method_decorator(archivist_required, name="dispatch")
class BucketSelectHTMXView(HtmxTemplateHelperMixin, View):
    """Return updated bucket select dropdown for upload modal."""

    def get(self, request):
        """Render bucket select dropdown."""
        bucket_select_html = self.render_bucket_select_template(
            request, active_bucket=self.get_active_bucket(request), oob=False
        )
        return HttpResponse(bucket_select_html)


@archivist_required
def file_info_htmx(request, bucket_type, object_path):
    """Provide file metadata details via HTMX."""
    bucket_service = BucketService(skip_bucket_check=True)
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
