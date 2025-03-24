import logging
import json
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from lacos.storage.services.upload_service import UploadService
from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.collection_service import CollectionService
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)

# Singleton instances
_upload_service = None
_base_storage_service = None
_collection_service = None
_bucket_service = None

def get_upload_service():
    global _upload_service
    if _upload_service is None:
        _upload_service = UploadService()
    return _upload_service

def get_base_storage_service():
    global _base_storage_service
    if _base_storage_service is None:
        _base_storage_service = BaseStorageService()
    return _base_storage_service

def get_collection_service():
    global _collection_service
    if _collection_service is None:
        _collection_service = CollectionService()
    return _collection_service

def get_bucket_service():
    global _bucket_service
    if _bucket_service is None:
        _bucket_service = BucketService()
    return _bucket_service

@login_required
@require_http_methods(["POST"])
def get_presigned_urls(request):
    """
    Generate presigned URLs for direct browser-to-S3 uploads.
    
    This view accepts a list of files and their paths and returns presigned URLs
    that the browser can use to upload directly to S3.
    
    This view directly uses the UploadService to generate presigned URLs.
    """
    # Check if we're receiving JSON data
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            folder_name = data.get('folder_name')
            files_metadata = data.get('files_metadata')
            files_json = json.dumps(files_metadata) if files_metadata else None
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON format"}, status=400)
    else:
        # Get from regular form data
        folder_name = request.POST.get("folder_name")
        files_json = request.POST.get("files_metadata")
    
    is_htmx = request.headers.get('HX-Request') == 'true'
    logger.info(f"HTMX request detected: {is_htmx}")
    logger.info(f"Content type: {request.content_type}")
    
    # Validate required parameters
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
    
    # Use the singleton upload service
    try:
        upload_service = get_upload_service()
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
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            # Try to parse from POST data
            uploaded_files_json = request.POST.get('uploaded_files')
            if uploaded_files_json:
                data = {'s3_keys': json.loads(uploaded_files_json)}
            else:
                return JsonResponse({"success": False, "error": "No uploaded_files provided"})
                
        s3_keys = data.get("s3_keys", [])
        
        logger.info(f"Received verification request with content type: {request.content_type}")
        logger.info(f"S3 keys to verify: {len(s3_keys)}")
        
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "Invalid JSON"})
    
    if not s3_keys:
        logger.warning("No S3 keys provided in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "No S3 keys provided"})
    
    logger.info(f"Verifying {len(s3_keys)} uploaded files")
    
    # Directly use the UploadService to verify each file
    try:
        upload_service = get_upload_service()
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


# ----- Multipart Upload Views -----

@login_required
@require_http_methods(["POST"])
def initialize_multipart_upload(request):
    """
    Initialize a multipart upload to S3.
    
    This view is called to start a multipart upload process for large files.
    It initializes the upload in S3 and returns an upload ID that will be used
    for subsequent part uploads.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        file_name = data.get("file_name")
        file_type = data.get("file_type")
        path_prefix = data.get("path_prefix")
        
        # Validate required fields
        if not file_name or not file_type:
            error_message = "File name and type are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        logger.info(f"Initializing multipart upload for {file_name}")
        
        # Use the upload service to initialize the multipart upload
        upload_service = get_upload_service()
        result = upload_service.initialize_multipart_upload(
            file_name=file_name,
            file_type=file_type,
            path_prefix=path_prefix
        )
        
        if result["success"]:
            logger.info(f"Multipart upload initialized with ID: {result['upload_id']}")
            return JsonResponse(result)
        else:
            logger.error(f"Failed to initialize multipart upload: {result.get('error')}")
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error initializing multipart upload: {str(e)}"
        logger.error(error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
@require_http_methods(["POST"])
def get_part_upload_urls(request):
    """
    Generate presigned URLs for each part of a multipart upload.
    
    This view is called after a multipart upload has been initialized to get
    presigned URLs for uploading each part of the file directly to S3.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        s3_key = data.get("s3_key")
        upload_id = data.get("upload_id")
        part_count = data.get("part_count")
        expiration = data.get("expiration", 3600)  # Default to 1 hour
        
        # Validate required fields
        if not s3_key or not upload_id or not part_count:
            error_message = "S3 key, upload ID, and part count are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        # Validate part count
        try:
            part_count = int(part_count)
            if part_count <= 0 or part_count > 10000:  # S3 allows up to 10,000 parts
                raise ValueError("Part count must be between 1 and 10,000")
        except (ValueError, TypeError) as e:
            error_message = f"Invalid part count: {str(e)}"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        logger.info(f"Generating {part_count} part upload URLs for {s3_key}")
        
        # Use the upload service to get presigned URLs for each part
        upload_service = get_upload_service()
        result = upload_service.get_upload_part_urls(
            s3_key=s3_key,
            upload_id=upload_id,
            part_count=part_count,
            expiration=expiration
        )
        
        if result["success"]:
            logger.info(f"Generated {len(result['presigned_urls'])} part upload URLs")
            return JsonResponse(result)
        else:
            logger.error(f"Failed to generate part upload URLs: {result.get('error')}")
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error generating part upload URLs: {str(e)}"
        logger.error(error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
@require_http_methods(["POST"])
def complete_multipart_upload(request):
    """
    Complete a multipart upload by assembling all uploaded parts.
    
    This view is called after all parts have been uploaded to complete the
    multipart upload process and finalize the file in S3.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        s3_key = data.get("s3_key")
        upload_id = data.get("upload_id")
        parts = data.get("parts")
        
        # Validate required fields
        if not s3_key or not upload_id or not parts:
            error_message = "S3 key, upload ID, and parts are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        # Validate parts structure
        if not isinstance(parts, list) or not all(
            isinstance(part, dict) and 'part_number' in part and 'etag' in part
            for part in parts
        ):
            error_message = "Parts must be a list of objects with part_number and etag properties"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        logger.info(f"Completing multipart upload for {s3_key} with {len(parts)} parts")
        
        # Use the upload service to complete the multipart upload
        upload_service = get_upload_service()
        result = upload_service.complete_multipart_upload(
            s3_key=s3_key,
            upload_id=upload_id,
            parts=parts
        )
        
        if result["success"]:
            logger.info(f"Multipart upload completed for {s3_key}")
            return JsonResponse(result)
        else:
            logger.error(f"Failed to complete multipart upload: {result.get('error')}")
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error completing multipart upload: {str(e)}"
        logger.error(error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
@require_http_methods(["POST"])
def abort_multipart_upload(request):
    """
    Abort a multipart upload and clean up any uploaded parts.
    
    This view is called to cancel a multipart upload process and remove
    any partially uploaded parts from S3.
    """
    try:
        # Parse request data
        data = json.loads(request.body)
        s3_key = data.get("s3_key")
        upload_id = data.get("upload_id")
        
        # Validate required fields
        if not s3_key or not upload_id:
            error_message = "S3 key and upload ID are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        logger.info(f"Aborting multipart upload for {s3_key}")
        
        # Use the upload service to abort the multipart upload
        upload_service = get_upload_service()
        result = upload_service.abort_multipart_upload(
            s3_key=s3_key,
            upload_id=upload_id
        )
        
        if result["success"]:
            logger.info(f"Multipart upload aborted for {s3_key}")
            return JsonResponse(result)
        else:
            logger.error(f"Failed to abort multipart upload: {result.get('error')}")
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error aborting multipart upload: {str(e)}"
        logger.error(error_message)
        return JsonResponse({"success": False, "error": error_message})


@login_required
@require_http_methods(["GET"])
def list_multipart_uploads(request):
    """
    List all in-progress multipart uploads.
    
    This view returns a list of all multipart uploads that have been
    initialized but not yet completed or aborted.
    """
    try:
        logger.info("Listing in-progress multipart uploads")
        
        # Use the upload service to list multipart uploads
        upload_service = get_upload_service()
        result = upload_service.list_multipart_uploads()
        
        if result["success"]:
            logger.info(f"Found {result.get('count', 0)} in-progress multipart uploads")
            return JsonResponse(result)
        else:
            logger.error(f"Failed to list multipart uploads: {result.get('error')}")
            return JsonResponse(result)
    
    except Exception as e:
        error_message = f"Error listing multipart uploads: {str(e)}"
        logger.error(error_message)
        return JsonResponse({"success": False, "error": error_message}) 