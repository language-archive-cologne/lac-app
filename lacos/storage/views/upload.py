from django.shortcuts import render
import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.upload_service import UploadService

logger = logging.getLogger(__name__)


@login_required
def upload_form(request):
    """
    Render the upload form for uploading folders to the ingest bucket.
    """
    return render(request, "upload/upload_form.html")


@login_required
@require_http_methods(["POST"])
def upload_folder(request):
    """
    Handle the upload of multiple files maintaining their folder structure to the ingest bucket.
    """
    folder_name = request.POST.get("folder_name")
    files = request.FILES.getlist("files")
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    logger.info(f"HTMX request detected: {is_htmx}")
    
    if not folder_name:
        messages.error(request, "Folder name is required")
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False,
                "message": "Folder name is required"
            })
        return redirect("storage:upload_form")
    
    if not files:
        messages.error(request, "No files selected")
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False,
                "message": "No files selected"
            })
        return redirect("storage:upload_form")
    
    logger.info(f"Received upload request for folder: {folder_name} with {len(files)} files")
    
    # Log all POST data for debugging
    logger.info("="*50)
    logger.info("DEBUG - REQUEST POST DATA:")
    for key in request.POST:
        if key.startswith('file_paths') or key == 'folder_name':
            logger.info(f"  {key}: {request.POST[key]}")
    logger.info("="*50)
    
    # Log all files information
    logger.info("DEBUG - FILES INFORMATION:")
    for i, file in enumerate(files):
        logger.info(f"  File {i}: name={file.name}, size={file.size}, content_type={file.content_type}")
    logger.info("="*50)
    
    # Extract file paths from the request - now using JSON array
    file_paths = {}
    file_paths_json = request.POST.get('file_paths_json')
    file_names_json = request.POST.get('file_names_json')
    
    if file_paths_json and file_names_json:
        try:
            import json
            paths_list = json.loads(file_paths_json)
            names_list = json.loads(file_names_json)
            
            logger.info(f"Parsed JSON paths list with {len(paths_list)} items")
            logger.info(f"Parsed JSON names list with {len(names_list)} items")
            
            # First, create a mapping between Django's file names and the original file names
            # Django might add suffixes like '_2' to disambiguate files with the same name
            django_file_map = {}
            original_name_map = {}
            
            # Create a list of all uploaded original filenames (from names_list)
            # and all the Django-modified filenames (from files list)
            django_filenames = [f.name for f in files]
            
            logger.info("Django received filenames: " + str(django_filenames))
            logger.info("Original filenames: " + str(names_list))
            
            # Match original filenames with Django filenames
            for i, original_name in enumerate(names_list):
                if i < len(django_filenames):
                    django_name = django_filenames[i]
                    django_file_map[original_name] = django_name
                    original_name_map[django_name] = original_name
                    logger.info(f"Mapped original name '{original_name}' to Django name '{django_name}'")
            
            # Now create the file paths using the correct Django filenames
            for i, path in enumerate(paths_list):
                if i < len(names_list):
                    original_name = names_list[i]
                    if original_name in django_file_map:
                        django_name = django_file_map[original_name]
                        file_paths[path] = django_name
                        logger.info(f"Mapped path '{path}' to Django file '{django_name}' (original: '{original_name}')")
                    else:
                        logger.warning(f"Could not find Django filename for original name '{original_name}'")
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON data: {e}")
    else:
        logger.warning("Missing file_paths_json or file_names_json in request")
    
    # Log summary of file paths
    logger.info(f"Extracted path information for {len(file_paths)}/{len(files)} files")
    
    # Upload files directly to S3 without saving to disk first
    upload_service = UploadService()
    result = upload_service.upload_files_directly(files, folder_name, file_paths=file_paths)
    
    if result["success"]:
        logger.info(f"Successfully uploaded folder {folder_name} to ingest bucket")
        
        # Build the success message, making sure all expected keys are available
        target_prefix = result.get('target_prefix', folder_name + '/')
        success_message = (
            f"Successfully uploaded {result['total_files']} files "
            f"({result['total_size_formatted']}) to {result['target_bucket']}/{target_prefix}"
        )
        messages.success(request, success_message)
        
        if is_htmx:
            # Prepare redirect URL
            dashboard_url = request.build_absolute_uri('/storage/dashboard/')
            logger.info(f"Setting redirect URL: {dashboard_url}")
            
            # Render the success template
            response = render(request, "upload/upload_status.html", {
                "success": True,
                "message": success_message,
                "result": result,
                "redirect_url": dashboard_url  # Add this for template use if needed
            })
            
            # Set HTMX headers for client-side redirection
            response['HX-Redirect'] = dashboard_url
            logger.info("HX-Redirect header set, expecting client redirect")
            
            # Also set a trigger for display of messages
            response['HX-Trigger'] = json.dumps({
                'showMessage': {
                    'level': 'success',
                    'message': success_message
                },
                'redirectNow': {
                    'url': dashboard_url
                }
            })
            
            return response
        return redirect("storage:archivist_dashboard")
    else:
        error_message = f"Failed to upload folder: {result.get('error', 'Unknown error')}"
        logger.error(error_message)
        messages.error(request, error_message)
        
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False,
                "message": error_message
            })
        return redirect("storage:upload_form")


@login_required
def upload_success(request):
    """
    Render the upload success page.
    """
    return render(request, "upload/upload_success.html")


@login_required
def archivist_dashboard(request):
    """
    Render the archivist dashboard showing both ingest and production buckets.
    This view displays the folder structure of both buckets side by side,
    allowing the archivist to view, move, and manage files between buckets.
    """
    bucket_service = BucketService()
    
    # Get folder structure for both buckets
    ingest_structure = bucket_service.get_folder_structure(bucket_service.ingest_bucket)
    production_structure = bucket_service.get_folder_structure(bucket_service.production_bucket)
    
    # Check for success message
    message = request.GET.get('message', None)
    
    return render(
        request,
        "dashboard/archivist_dashboard.html",
        {
            "ingest_structure": ingest_structure,
            "production_structure": production_structure,
            "message": message,
        },
    )
