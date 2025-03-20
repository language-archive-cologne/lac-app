from django.shortcuts import render
import logging
import json

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)



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
            "dashboard/file_error.html",
            {"error": file_data["error"]},
        )
    
    # Determine the content type
    content_type = file_data["metadata"]["content_type"]
    
    # Render the appropriate template based on the content type
    if content_type.startswith("text/") or content_type in ["application/json", "application/xml"]:
        # For text files, render the content directly
        return render(
            request,
            "dashboard/file_content.html",
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
            "dashboard/file_download.html",
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
        
        # Store message in Django's message framework for page reloads
        messages.success(request, message)
        
        if is_htmx:
            # When deleting files, we want a targeted response (empty for replacement)
            if not is_directory:
                # For single file deletion, just return empty content to remove the element
                response = HttpResponse('', status=200)
                # Explicitly trigger the message display without waiting for page reload
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
                    "dashboard/folder_structure_partial.html",
                    {
                        "structure": structure,
                        "bucket_type": bucket_type
                    }
                )
                
                # Set HTMX headers to trigger the message display
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
