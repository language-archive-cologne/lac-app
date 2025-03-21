import logging
import json
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from lacos.storage.services.upload_service import UploadService

logger = logging.getLogger(__name__)


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
            
            # Ensure the response includes the full presigned post data including s3_key
            return JsonResponse({
                "success": True, 
                "presigned_posts": result["presigned_posts"],
                "total_urls": result["total_urls"],
                "total_failures": result.get("total_failures", 0),
                "failures": result.get("failures", [])
            })
        else:
            error_message = f"Failed to generate presigned URLs: {result.get('error', 'Unknown error')}"
            logger.error(error_message)
            messages.error(request, error_message)
            
            if is_htmx:
                return render(request, "upload/upload_status.html", {
                    "success": False, "message": error_message
                })
            return JsonResponse({"success": False, "error": error_message, "failures": result.get("failures", [])})
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
        total_size = 0
        
        for s3_key in s3_keys:
            # Log the exact head_object request being made
            logger.info(f"Checking S3 key: {s3_key} in bucket: {upload_service.ingest_bucket}")
            try:
                # Directly test the S3 client
                response = upload_service.s3_client.head_object(
                    Bucket=upload_service.ingest_bucket,
                    Key=s3_key
                )
                logger.info(f"S3 head_object response: {response}")
            except Exception as e:
                logger.error(f"Error in head_object: {str(e)}")
            
            # Get the verification result from the service
            result = upload_service.mark_upload_complete(s3_key)
            
            # Ensure the result is serializable by converting to dict if needed
            if not isinstance(result, dict):
                # This is primarily a safeguard for testing environments
                logger.warning(f"Result for {s3_key} is not a dict, converting...")
                serializable_result = {
                    "success": result.get("success", False),
                    "exists": result.get("exists", False),
                    "s3_key": s3_key
                }
                results.append(serializable_result)
            else:
                results.append(result)
            
            if result.get("exists", False):
                total_verified += 1
                # Add file size to total if available
                if "file_size" in result:
                    total_size += result["file_size"]
            else:
                total_failed += 1
                success = False
            
        # Format the total size as a human-readable string
        total_size_formatted = "0 B"
        if total_size > 0:
            try:
                total_size_formatted = upload_service._format_size(total_size)
            except Exception as e:
                logger.warning(f"Error formatting size: {str(e)}")
                total_size_formatted = f"{total_size} B"
        
        # Return the aggregated results with detailed information
        return JsonResponse({
            "success": success,
            "results": results,
            "total_verified": total_verified,
            "total_failed": total_failed,
            "total_size": total_size,
            "total_size_formatted": total_size_formatted
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