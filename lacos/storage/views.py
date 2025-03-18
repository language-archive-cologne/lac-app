from django.shortcuts import render
import logging
import os
import tempfile
import shutil
from pathlib import Path
import json

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@login_required
def upload_form(request):
    """
    Render the upload form for uploading folders to the ingest bucket.
    """
    return render(request, "upload_form.html")


@login_required
@require_http_methods(["POST"])
def upload_folder(request):
    """
    Handle the upload of multiple files maintaining their folder structure to the ingest bucket.
    """
    folder_name = request.POST.get("folder_name")
    files = request.FILES.getlist("files")
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if not folder_name:
        messages.error(request, "Folder name is required")
        if is_htmx:
            return render(request, "upload_status.html", {
                "success": False,
                "message": "Folder name is required"
            })
        return redirect("storage:upload_form")
    
    if not files:
        messages.error(request, "No files selected")
        if is_htmx:
            return render(request, "upload_status.html", {
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
    
    if file_paths_json:
        try:
            import json
            paths_list = json.loads(file_paths_json)
            logger.info(f"Parsed JSON paths list with {len(paths_list)} items")
            
            # Associate paths with files by index
            for i, file in enumerate(files):
                if i < len(paths_list):
                    file_paths[file.name] = paths_list[i]
                    logger.info(f"Mapped file {file.name} to path {paths_list[i]}")
                else:
                    logger.warning(f"No path information found for file {file.name} (index {i} out of range)")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing file_paths_json: {e}")
    else:
        logger.warning("No file_paths_json found in request")
    
    # Log summary of file paths
    logger.info(f"Extracted path information for {len(file_paths)}/{len(files)} files")
    
    # Upload files directly to S3 without saving to disk first
    bucket_service = BucketService()
    result = bucket_service.upload_files_directly(files, folder_name, file_paths=file_paths)
    
    if result["success"]:
        logger.info(f"Successfully uploaded folder {folder_name} to ingest bucket")
        success_message = (
            f"Successfully uploaded {result['total_files']} files "
            f"({result['total_size_formatted']}) to {result['target_bucket']}/{result['target_prefix']}"
        )
        messages.success(request, success_message)
        
        if is_htmx:
            response = render(request, "upload_status.html", {
                "success": True,
                "message": success_message,
                "result": result
            })
            response['HX-Redirect'] = request.build_absolute_uri('/storage/dashboard/')
            return response
        return redirect("storage:upload_success")
    else:
        error_message = f"Failed to upload folder: {result.get('error', 'Unknown error')}"
        logger.error(error_message)
        messages.error(request, error_message)
        
        if is_htmx:
            return render(request, "upload_status.html", {
                "success": False,
                "message": error_message
            })
        return redirect("storage:upload_form")


@login_required
def upload_success(request):
    """
    Render the upload success page.
    """
    return render(request, "upload_success.html")


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
        "archivist_dashboard.html",
        {
            "ingest_structure": ingest_structure,
            "production_structure": production_structure,
            "message": message,
        },
    )


@login_required
@require_http_methods(["POST"])
def move_to_production(request, folder_path):
    """
    Move a folder from the ingest bucket to the production bucket.
    This involves standardizing the OCFL structure according to the requirements.
    """
    bucket_service = BucketService()
    
    # URL decode the folder path
    folder_path = folder_path.replace('%2F', '/')
    
    # Move the folder to production
    result = bucket_service.move_to_production(folder_path)
    
    if result["success"]:
        messages.success(request, result["message"])
        return redirect("storage:archivist_dashboard")
    else:
        messages.error(request, result["error"])
        return redirect("storage:archivist_dashboard")


@login_required
def file_content(request, bucket_type, file_path):
    """
    Get the content of a file from the specified bucket.
    """
    bucket_service = BucketService()
    
    # Determine which bucket to use
    bucket_name = bucket_service.ingest_bucket if bucket_type == "ingest" else bucket_service.production_bucket
    
    # URL decode the file path
    file_path = file_path.replace('%2F', '/')
    
    # Get the file content
    file_data = bucket_service.get_file_content(bucket_name, file_path)
    
    if "error" in file_data:
        return render(
            request,
            "file_error.html",
            {"error": file_data["error"]},
        )
    
    # Determine the content type
    content_type = file_data["metadata"]["content_type"]
    
    # Render the appropriate template based on the content type
    if content_type.startswith("text/") or content_type in ["application/json", "application/xml"]:
        # For text files, render the content directly
        return render(
            request,
            "file_content.html",
            {
                "file_path": file_path,
                "content": file_data["content"].decode("utf-8"),
                "content_type": content_type,
                "bucket_type": bucket_type,
            },
        )
    else:
        # For binary files, provide a download link
        return render(
            request,
            "file_download.html",
            {
                "file_path": file_path,
                "content_type": content_type,
                "bucket_type": bucket_type,
            },
        )


@login_required
@require_http_methods(["DELETE"])
def delete_object(request, bucket_type, object_type, object_path):
    """
    Delete an object (file or folder) from the specified bucket.
    """
    bucket_service = BucketService()
    
    # Determine which bucket to use
    bucket_name = bucket_service.ingest_bucket if bucket_type == "ingest" else bucket_service.production_bucket
    
    # URL decode the object path
    object_path = object_path.replace('%2F', '/')
    
    # Delete the object
    is_directory = object_type == "folder"
    result = bucket_service.delete_object(bucket_name, object_path, is_directory)
    
    # Check if this is an HTMX request
    is_htmx = request.headers.get('HX-Request') == 'true'
    
    if result["success"]:
        message = result["message"]
        messages.success(request, message)
        
        if is_htmx:
            # When deleting files, we want a targeted response (empty for replacement)
            if not is_directory:
                # For single file deletion, just return empty content to remove the element
                response = HttpResponse('', status=200)
                response['HX-Trigger'] = json.dumps({
                    "showMessage": {
                        "level": "success",
                        "message": message
                    }
                })
                return response
            else:
                # For directories, return the updated structure as before
                bucket_service = BucketService()
                
                # Get updated folder structure for the affected bucket
                if bucket_type == "ingest":
                    structure = bucket_service.get_folder_structure(bucket_service.ingest_bucket)
                    target_id = "ingest-structure"
                else:
                    structure = bucket_service.get_folder_structure(bucket_service.production_bucket)
                    target_id = "production-structure"
                    
                # Render the updated structure
                response = render(
                    request,
                    "folder_structure_partial.html",
                    {
                        "structure": structure,
                        "bucket_type": bucket_type
                    }
                )
                
                # Set HTMX headers to target the correct container
                response['HX-Trigger'] = json.dumps({
                    "showMessage": {
                        "level": "success",
                        "message": message
                    }
                })
                
                return response
        else:
            return redirect("storage:archivist_dashboard")
    else:
        error_message = f"Error: {result['error']}"
        messages.error(request, error_message)
        
        if is_htmx:
            # For errors, we can just return a message that will be displayed
            response = HttpResponse(error_message, status=400)
            response['HX-Trigger'] = json.dumps({
                "showMessage": {
                    "level": "error",
                    "message": error_message
                }
            })
            return response
        else:
            return redirect("storage:archivist_dashboard")
