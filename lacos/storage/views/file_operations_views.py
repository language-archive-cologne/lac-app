import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.urls import reverse

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@login_required
def move_to_production(request, folder_path):
    """
    Move a folder from the ingest bucket to the production bucket.
    
    This operation copies all files from the specified folder in the ingest bucket
    to the production bucket, maintaining the same folder structure.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})
    
    try:
        bucket_service = BucketService()
        
        # Add debug logging to trace the copying process
        logger.info(f"Preparing to move folder '{folder_path}' to production")
        
        # Trace the ingest bucket contents before copying
        ingest_contents = bucket_service.list_bucket_contents(bucket_service.ingest_bucket, folder_path)
        logger.info(f"Source folder contents in ingest bucket ({len(ingest_contents)} items):")
        for item in ingest_contents:
            logger.info(f"  {item.get('path')} - {'folder' if item.get('is_dir', False) else 'file'}")
        
        # Perform the direct move to production
        result = bucket_service.direct_move_to_production(folder_path)
        
        # Check the production bucket contents after copying
        if result.get("success", False):
            # Wait a moment for S3 consistency (especially important for MinIO)
            import time
            time.sleep(0.5)  # 500ms delay
            
            # Verify the production bucket contents
            production_contents = bucket_service.list_bucket_contents(bucket_service.production_bucket, folder_path)
            logger.info(f"Production bucket contents after copy ({len(production_contents)} items):")
            for item in production_contents:
                logger.info(f"  {item.get('path')} - {'folder' if item.get('is_dir', False) else 'file'}")
        
        # Check if this is an HTMX request
        is_htmx = request.headers.get('HX-Request') == 'true'
        
        if result.get("success", False):
            success_message = f"Successfully moved folder '{folder_path}' to production"
            logger.info(success_message)
            messages.success(request, success_message)
            
            # If HTMX request, return the updated production bucket contents
            if is_htmx:
                try:
                    # Add debug logging
                    logger.info(f"Getting updated production structure after move")
                    
                    # Get updated production bucket structure
                    production_structure = bucket_service.get_root_level_items(bucket_service.production_bucket)
                    
                    # Log the structure for debugging
                    logger.info(f"Production structure children count: {len(production_structure.get('children', []))}")
                    
                    # Return the complete rendered partial for the entire production bucket
                    response = render(request, 'dashboard/folder_structure_partial.html', {
                        'structure': production_structure,
                        'bucket_type': 'production'
                    })
                    
                    # Add a cache-busting header to force browser refresh
                    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    response['Pragma'] = 'no-cache'
                    response['Expires'] = '0'
                    
                    return response
                    
                except Exception as e:
                    logger.exception(f"Error refreshing production structure: {str(e)}")
                    # Fall back to redirect if there's an error updating the UI
                    redirect_url = reverse('storage:archivist_dashboard') + f"?message={success_message}"
                    return redirect(redirect_url)
            
            # Regular request - redirect to dashboard with success message
            redirect_url = reverse('storage:archivist_dashboard') + f"?message={success_message}"
            return redirect(redirect_url)
        else:
            error_message = f"Failed to move folder: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            # If HTMX request, return error message
            if is_htmx:
                return HttpResponse(error_message, status=400)
            
            # Regular request - redirect to dashboard
            return redirect(reverse('storage:archivist_dashboard'))
            
    except Exception as e:
        error_message = f"Error moving folder to production: {str(e)}"
        logger.exception(error_message)
        messages.error(request, error_message)
        
        # If HTMX request, return error message
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse(error_message, status=500)
        
        # Regular request - redirect to dashboard
        return redirect(reverse('storage:archivist_dashboard'))


@login_required
def file_content(request, bucket_type, file_path):
    """
    Retrieve and display the content of a file from a bucket.
    
    This view serves the content of a file directly to the browser.
    For binary files (images, etc.), it streams the content with the
    appropriate content type. For text files, it renders the content
    in a readable format.
    """
    try:
        bucket_service = BucketService()
        
        # Determine which bucket to use
        bucket = bucket_service.ingest_bucket
        if bucket_type == "production":
            bucket = bucket_service.production_bucket
        
        # Get file content and metadata
        result = bucket_service.get_file_content(bucket, file_path)
        
        if result.get("success", False):
            content_type = result.get("content_type", "application/octet-stream")
            content = result.get("content")
            
            # Return the file content with the appropriate content type
            response = HttpResponse(content, content_type=content_type)
            
            # Add content disposition header for download if requested
            if request.GET.get("download") == "true":
                filename = file_path.split("/")[-1]
                response["Content-Disposition"] = f'attachment; filename="{filename}"'
                
            return response
        else:
            error_message = f"Failed to retrieve file: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            return HttpResponse(error_message, status=404)
            
    except Exception as e:
        error_message = f"Error retrieving file content: {str(e)}"
        logger.exception(error_message)
        return HttpResponse(error_message, status=500)


@login_required
def delete_object(request, bucket_type, object_type, object_path):
    """
    Delete a file or folder from a bucket.
    
    This operation permanently deletes the specified object from the bucket.
    If the object is a folder, all contents will also be deleted.
    
    Args:
        bucket_type: "ingest" or "production"
        object_type: "file" or "folder"
        object_path: The path to the object within the bucket
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})
    
    try:
        bucket_service = BucketService()
        
        # Determine which bucket to use
        bucket_name = bucket_service.ingest_bucket
        if bucket_type == "production":
            bucket_name = bucket_service.production_bucket
        
        # Delete the object based on its type
        if object_type == "folder":
            result = bucket_service.delete_folder(bucket_name, object_path)
        else:  # file
            result = bucket_service.delete_file(bucket_name, object_path)
        
        if result.get("success", False):
            success_message = f"Successfully deleted {object_type} '{object_path}'"
            logger.info(success_message)
            messages.success(request, success_message)
            
            if request.headers.get('HX-Request') == 'true':
                # Return an empty response with 200 OK instead of 204 No Content
                return HttpResponse("", status=200)  # Empty string but status 200
            
            return JsonResponse({"success": True, "message": success_message})
        else:
            error_message = f"Failed to delete {object_type}: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            if request.headers.get('HX-Request') == 'true':
                return HttpResponse(error_message, status=400)
                
            return JsonResponse({"success": False, "error": error_message})
            
    except Exception as e:
        error_message = f"Error deleting {object_type}: {str(e)}"
        logger.exception(error_message)
        messages.error(request, error_message)
        
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse(error_message, status=500)
            
        return JsonResponse({"success": False, "error": error_message}) 