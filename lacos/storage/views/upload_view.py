import logging
import json
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.upload_service import UploadService
from django.conf import settings

logger = logging.getLogger(__name__)


@login_required
def upload_form(request):
    """
    Render the upload form for uploading folders to the ingest bucket.
    
    This is a simple view that renders the upload form HTML template.
    No business logic is performed here.
    """
    return render(request, "upload/upload_form.html")


@login_required
@require_http_methods(["POST"])
def get_presigned_urls(request):
    """
    Generate presigned URLs for direct browser-to-S3 uploads.
    
    This view accepts a list of files and their paths and returns presigned URLs
    that the browser can use to upload directly to S3.
    
    This view directly uses the UploadService to generate presigned URLs.
    """
    folder_name = request.POST.get("folder_name")
    files_json = request.POST.get("files_metadata")
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    logger.info(f"HTMX request detected: {is_htmx}")
    
    # Validate request parameters
    if not folder_name:
        error_message = "Folder name is required"
        logger.warning(error_message)
        messages.error(request, error_message)
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False, "message": error_message
            })
        return JsonResponse({"success": False, "error": error_message})
    
    if not files_json:
        error_message = "No files metadata provided"
        logger.warning(error_message)
        messages.error(request, error_message)
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False, "message": error_message
            })
        return JsonResponse({"success": False, "error": error_message})
    
    # Parse file metadata
    try:
        files_metadata = json.loads(files_json)
    except json.JSONDecodeError as e:
        error_message = f"Invalid files metadata format: {e}"
        logger.error(error_message)
        messages.error(request, error_message)
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False, "message": error_message
            })
        return JsonResponse({"success": False, "error": error_message})
    
    logger.info(f"Generating presigned URLs for folder: {folder_name} with {len(files_metadata)} files")
    
    # Log sample files information for debugging
    if files_metadata:
        logger.debug(f"Sample file metadata: {files_metadata[0]}")
    
    # Directly use the UploadService to generate presigned URLs
    try:
        upload_service = UploadService()
        result = upload_service.generate_batch_presigned_posts(
            files_metadata=files_metadata,
            path_prefix=folder_name,
            expiration=3600  # 1 hour expiration
        )
        
        if result["success"]:
            logger.info(f"Successfully generated {result['total_urls']} presigned URLs")
            
            if is_htmx:
                return render(request, "upload/presigned_urls.html", {
                    "success": True,
                    "result": result
                })
            return JsonResponse({
                "success": True, 
                "presigned_posts": result["presigned_posts"],
                "total_urls": result["total_urls"]
            })
        else:
            error_message = f"Failed to generate presigned URLs: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            if is_htmx:
                return render(request, "upload/upload_status.html", {
                    "success": False, "message": error_message
                })
            return JsonResponse({"success": False, "error": error_message})
    except Exception as service_error:
        # Handle service call errors
        error_message = f"Service error: {str(service_error)}"
        logger.error(error_message)
        messages.error(request, error_message)
        
        if is_htmx:
            return render(request, "upload/upload_status.html", {
                "success": False, "message": error_message
            })
        return JsonResponse({"success": False, "error": error_message})


@login_required
def mark_uploads_complete(request):
    """
    Mark uploads as complete and verify the files in S3.
    
    This view is called by the client after all uploads are complete to verify
    that the files were successfully uploaded to S3.
    
    This view directly uses the UploadService to verify uploaded files.
    """
    # Check for valid request method
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Method not allowed"})
    
    # Parse and validate request body
    try:
        data = json.loads(request.body)
        s3_keys = data.get("s3_keys", [])
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "Invalid JSON"})
    
    if not s3_keys:
        logger.warning("No S3 keys provided in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "No S3 keys provided"})
    
    logger.info(f"Verifying {len(s3_keys)} uploaded files")
    
    # Directly use the UploadService to verify each file
    try:
        upload_service = UploadService()
        results = []
        success = True
        total_verified = 0
        total_failed = 0
        
        for s3_key in s3_keys:
            result = upload_service.mark_upload_complete(s3_key)
            results.append(result)
            if result.get("exists", False):
                total_verified += 1
            else:
                total_failed += 1
                success = False
            
        # Return the aggregated results
        return JsonResponse({
            "success": success,
            "results": results,
            "total_verified": total_verified,
            "total_failed": total_failed
        })
    
    except Exception as service_error:
        # Handle service call errors
        error_message = f"Failed to verify uploads: {str(service_error)}"
        logger.error(error_message)
        return JsonResponse({
            "success": False,
            "error": error_message,
            "total_verified": 0,
            "total_failed": len(s3_keys)
        })


@login_required
@require_http_methods(["POST"])
def copy_object_to_production(request):
    """
    Copy an object from the ingest bucket to the production bucket.
    
    This view directly uses the UploadService to copy objects between buckets.
    
    Request parameters:
    - source_key: The object key in the ingest bucket
    - dest_key: (optional) The destination key in the production bucket,
                defaults to the same as source_key if not provided
    """
    # Get parameters from request
    source_key = request.POST.get('source_key')
    dest_key = request.POST.get('dest_key', source_key)  # Use source key if dest not specified
    
    # Validate parameters
    if not source_key:
        error_message = "Source key is required"
        logger.warning(error_message)
        messages.error(request, error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    logger.info(f"Copying object from ingest/{source_key} to production/{dest_key}")
    
    # Directly use the UploadService to copy the object
    try:
        upload_service = UploadService()
        result = upload_service.copy_object(
            source_key=source_key,
            dest_key=dest_key,
            source_bucket=None,  # Use default ingest bucket
            dest_bucket=None     # Use default production bucket
        )
        
        if result.get("success", False):
            success_message = f"Successfully copied {source_key} to production bucket"
            logger.info(success_message)
            messages.success(request, success_message)
            return JsonResponse({
                "success": True,
                "message": success_message,
                "source_key": source_key,
                "dest_key": dest_key
            })
        else:
            error_message = f"Failed to copy object: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            return JsonResponse({"success": False, "error": error_message})
    
    except Exception as service_error:
        # Handle service call errors
        error_message = f"Service error: {str(service_error)}"
        logger.error(error_message)
        messages.error(request, error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
def upload_success(request):
    """
    Render the upload success page.
    
    This is a simple view that renders the success confirmation template.
    No business logic is performed here.
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
