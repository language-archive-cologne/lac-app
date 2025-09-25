import logging
import ast
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService
from lacos.common.mixins import HtmxTemplateHelperMixin
from django.http import HttpResponse, JsonResponse, RawPostDataException
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
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
class RenameBucketHTMXView(HtmxTemplateHelperMixin, View):
    """Handle HTMX bucket rename requests."""

    def post(self, request, bucket_name):
        try:
            new_name = ''
            try:
                if request.body:
                    raw_body = request.body.decode(request.encoding or 'utf-8')
                    if request.content_type == 'application/json':
                        payload = json.loads(raw_body)
                        new_name = (payload.get('prompt') or payload.get('newName') or '').strip()
                    elif request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
                        from django.http import QueryDict
                        form_data = QueryDict(raw_body)
                        new_name = (form_data.get('prompt') or form_data.get('newName') or '').strip()
                        if not new_name and raw_body.startswith('{'):
                            try:
                                parsed = json.loads(raw_body)
                            except ValueError:
                                try:
                                    parsed = ast.literal_eval(raw_body)
                                except (ValueError, SyntaxError):
                                    parsed = {}
                            new_name = (parsed.get('prompt') or parsed.get('newName') or '').strip()
            except (ValueError, TypeError, RawPostDataException):
                new_name = ''

            if not new_name:
                new_name = (request.POST.get('prompt') or request.POST.get('newName') or '').strip()
            if not new_name:
                return HttpResponse("Bucket name is required", status=400)

            bucket_service = BucketService()
            result = bucket_service.rename_bucket(bucket_name, new_name)

            if not result.get('success'):
                return HttpResponse(result.get('error', 'Rename failed'), status=400)

            content_html = self.render_bucket_content_template(request, new_name)

            response_html = self.build_bucket_tabs_oob_response(
                main_html=content_html,
                request=request,
                active_bucket=new_name,
                success_message=result.get('message')
            )

            response = HttpResponse(response_html)
            response['HX-Trigger'] = json.dumps({
                'bucketRenamed': {
                    'oldName': bucket_name,
                    'newName': new_name,
                }
            })
            return response

        except Exception as e:
            logger.exception(f"Error renaming bucket {bucket_name}: {str(e)}")
            return HttpResponse(f"Error renaming bucket: {str(e)}", status=500)
