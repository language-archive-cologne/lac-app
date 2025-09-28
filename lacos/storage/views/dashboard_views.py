import logging
import ast
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService
from lacos.common.mixins import HtmxTemplateHelperMixin
from django.http import HttpResponse, JsonResponse, QueryDict
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.template.loader import render_to_string
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils.text import slugify
import json

logger = logging.getLogger(__name__)


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing all workspace buckets.
    Only loads root level items initially for better performance.
    """
    bucket_service = BucketService()

    try:
        # Get root level items for all workspace buckets
        bucket_structures = {}
        for bucket_name in bucket_service.get_all_accessible_buckets():
            try:
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
        ingest_structure = {"type": "folder", "name": bucket_service.ingest_bucket, "path": "", "children": []}
        production_structure = {"type": "folder", "name": bucket_service.production_bucket, "path": "", "children": []}

    # Check for success message
    message = request.GET.get('message', None)

    return render(
        request,
        "dashboard/archivist_dashboard.html",
        {
            "bucket_structures": bucket_structures,
            "workspace_buckets": bucket_service.get_all_accessible_buckets(),
            "ocfl_buckets": bucket_service.ocfl_buckets,
            # Legacy backward compatibility
            "ingest_structure": ingest_structure,
            "production_structure": production_structure,
            "message": message,
        },
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
        logger.info(f"Loading folder contents for {bucket_type} bucket, path: {folder_path}")
        
        # Get folder contents
        folder_contents = bucket_service.get_folder_contents(bucket, folder_path)
        logger.info(f"Folder contents for {folder_path}: {folder_contents}")
        
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
        
        if bucket_type == "ingest":
            structure = bucket_service.get_root_level_items(bucket_service.ingest_bucket)
        elif bucket_type == "production":
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
            # Get the current active bucket from form data
            current_active_bucket = request.POST.get('currentActiveBucket')

            # If no current bucket (first bucket creation), use the new bucket
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
