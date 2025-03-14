from django.shortcuts import render
import logging
import os
import tempfile
import shutil
from pathlib import Path

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required

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
    if request.method == "POST":
        folder_name = request.POST.get("folder_name")
        files = request.FILES.getlist("files")
        
        if not folder_name:
            messages.error(request, "Folder name is required")
            return redirect("storage:upload_form")
        
        if not files:
            messages.error(request, "No files selected")
            return redirect("storage:upload_form")
        
        logger.info(f"Received upload request for folder: {folder_name} with {len(files)} files")
        
        # Create a temporary directory to store the uploaded files
        with tempfile.TemporaryDirectory() as temp_dir:
            folder_path = os.path.join(temp_dir, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            
            # Process each uploaded file
            for file in files:
                # Extract the relative path from the filename
                file_path = file.name
                
                if not file_path:
                    continue
                    
                # Create the full path for the file
                full_path = os.path.join(folder_path, file_path)
                
                # Create directories if they don't exist
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                # Save the file
                with open(full_path, "wb") as f:
                    for chunk in file.chunks():
                        f.write(chunk)
                
                logger.info(f"Saved file {file_path} to {full_path}")
            
            # Upload the folder to the ingest bucket
            bucket_service = BucketService()
            result = bucket_service.upload_folder_to_bucket(folder_path)
            
            if result["success"]:
                logger.info(f"Successfully uploaded folder {folder_name} to ingest bucket")
                messages.success(
                    request, 
                    f"Successfully uploaded {result['total_files']} files "
                    f"({result['total_size_formatted']}) to {result['target_bucket']}/{result['target_prefix']}"
                )
                return redirect("storage:upload_success")
            else:
                logger.error(f"Failed to upload folder: {result.get('error', 'Unknown error')}")
                messages.error(request, f"Failed to upload folder: {result.get('error', 'Unknown error')}")
                return redirect("storage:upload_form")
    
    # Should not reach here, but just in case
    return redirect("storage:upload_form")


@login_required
def upload_success(request):
    """
    Render the upload success page.
    """
    return render(request, "storage/upload_success.html")


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
        "storage/archivist_dashboard.html",
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
        return redirect(f"/storage/dashboard?message={result['message']}")
    else:
        messages.error(request, result["error"])
        return redirect("/storage/dashboard")


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
            "storage/file_error.html",
            {"error": file_data["error"]},
        )
    
    # Determine the content type
    content_type = file_data["metadata"]["content_type"]
    
    # Render the appropriate template based on the content type
    if content_type.startswith("text/") or content_type in ["application/json", "application/xml"]:
        # For text files, render the content directly
        return render(
            request,
            "storage/file_content.html",
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
            "storage/file_download.html",
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
    
    if result["success"]:
        return redirect(f"/storage/dashboard?message={result['message']}")
    else:
        return redirect(f"/storage/dashboard?message=Error: {result['error']}")
