import logging
import json
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from lacos.storage.permissions import (
    archivist_required,
    can_manage_collection,
    manager_or_archivist_required,
    resolve_collection_from_path,
)
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from lacos.storage.services.upload_service import UploadService
from lacos.storage.services.upload_verification_service import UploadVerificationService
from lacos.storage.models import UploadSession, S3FileObject

logger = logging.getLogger(__name__)

# Singleton instances
_upload_service = None

def get_upload_service():
    global _upload_service
    if _upload_service is None:
        _upload_service = UploadService()
    return _upload_service

def _ensure_collection_access(request, *, path_hint: str | None = None, s3_keys: list | None = None):
    if path_hint is not None:
        collection = resolve_collection_from_path(path_hint)
        if not can_manage_collection(request.user, collection):
            raise PermissionDenied("Collection manager access required.")
        return None
    if s3_keys:
        if isinstance(s3_keys, (str, bytes)):
            s3_keys = [s3_keys]
        for key in s3_keys:
            collection = resolve_collection_from_path(key)
            if not can_manage_collection(request.user, collection):
                raise PermissionDenied("Collection manager access required.")
    return None


@manager_or_archivist_required
@require_http_methods(["POST"])
def get_presigned_urls(request):
    """
    Generate presigned URLs for direct browser-to-S3 uploads.
    
    This view accepts a list of files and their paths and returns presigned URLs
    that the browser can use to upload directly to S3.
    
    This view directly uses the UploadService to generate presigned URLs and
    creates UploadSession/S3FileObject records for per-file audit.
    """
    # Check if we're receiving JSON data
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            folder_name = data.get('folder_name')
            bucket_name = data.get('bucket_name')
            files_metadata = data.get('files_metadata')
            files_json = json.dumps(files_metadata) if files_metadata else None
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "Invalid JSON format"}, status=400)
    else:
        # Get from regular form data
        folder_name = request.POST.get("folder_name")
        bucket_name = request.POST.get("bucket_name")
        files_json = request.POST.get("files_metadata")
    
    logger.info("Received presigned URL request", extra={"content_type": request.content_type})
    
    # folder_name is optional - if empty, files go to bucket root
    # If uploading a folder structure, the path is preserved from files_metadata
    if not folder_name:
        folder_name = ""  # Empty string means bucket root
    
    if not files_json:
        error_message = "No files metadata provided"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    # Parse file metadata
    try:
        files_metadata = json.loads(files_json)
    except json.JSONDecodeError as e:
        error_message = f"Invalid files metadata format: {e}"
        logger.error("Invalid files metadata format", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})
    
    access_error = _ensure_collection_access(request, path_hint=folder_name)
    if access_error:
        return access_error

    logger.info("Generating presigned URLs for folder", extra={"folder_name": folder_name, "file_count": len(files_metadata)})
    
    # Log sample files information for debugging
    if files_metadata:
        logger.debug("Sample file metadata", extra={"sample": files_metadata[0]})
    
    # Use the singleton upload service
    try:
        upload_service = get_upload_service()
        upload_session = None

        def _extract_original_path(file_meta):
            return file_meta.get("path") or file_meta.get("file_path") or file_meta.get("relative_path") or ""

        def _build_s3_key(file_meta):
            file_name = file_meta.get("file_name")
            if not file_name:
                return None
            file_path = _extract_original_path(file_meta)
            effective_path_prefix = folder_name
            if file_path:
                if file_path.endswith(file_name):
                    file_path = file_path[:-len(file_name)].rstrip('/')
                if file_path:
                    effective_path_prefix = (
                        f"{effective_path_prefix}/{file_path}" if effective_path_prefix else file_path
                    )
            return upload_service._generate_file_key(file_name, effective_path_prefix)

        def _resolve_user():
            user = getattr(request, "user", None)
            if user is None:
                return None
            try:
                if not user.is_authenticated:
                    return None
            except Exception:
                return None
            user_obj = getattr(user, "_wrapped", user)
            user_model = get_user_model()
            if not hasattr(user_obj, "_meta"):
                return None
            if not isinstance(user_obj, user_model):
                return None
            return user_obj

        user_obj = _resolve_user()
        if user_obj:
            total_size = 0
            for file_meta in files_metadata:
                size_value = file_meta.get("file_size", file_meta.get("size", 0)) or 0
                total_size += int(size_value)

            with transaction.atomic():
                upload_session = UploadSession.objects.create(
                    user=user_obj,
                    folder_name=folder_name,
                    bucket_name=bucket_name or upload_service.ingest_bucket,
                    total_files=0,
                    total_size_bytes=total_size,
                )

                file_objects = []
                for file_meta in files_metadata:
                    file_name = file_meta.get("file_name")
                    if not file_name:
                        logger.warning("Skipping upload session record for file with missing name.")
                        continue

                    file_type = file_meta.get("file_type") or ""
                    original_path = _extract_original_path(file_meta) or file_name
                    s3_key = _build_s3_key(file_meta)
                    if not s3_key:
                        logger.warning("Skipping upload session record for %s due to missing S3 key.", file_name)
                        continue

                    file_size = file_meta.get("file_size", file_meta.get("size", 0)) or 0
                    status = "pending"
                    error_message = ""
                    if not file_type:
                        status = "failed"
                        error_message = "Missing file_type"

                    file_objects.append(S3FileObject(
                        session=upload_session,
                        bucket_name=bucket_name or "",
                        file_name=file_name,
                        original_path=original_path,
                        s3_key=s3_key,
                        file_size_bytes=int(file_size),
                        content_type=file_type,
                        status=status,
                        error_message=error_message,
                    ))

                if file_objects:
                    S3FileObject.objects.bulk_create(file_objects)
                    upload_session.total_files = len(file_objects)
                    upload_session.save(update_fields=["total_files"])

        result = upload_service.generate_batch_presigned_posts(
            files_metadata=files_metadata,
            path_prefix=folder_name,
            bucket_name=bucket_name,
            expiration=3600  # 1 hour expiration
        )

        if upload_session and result.get("failures"):
            for failure in result.get("failures", []):
                file_meta = failure.get("file_meta", {})
                s3_key = _build_s3_key(file_meta)
                if not s3_key:
                    continue
                S3FileObject.objects.filter(session=upload_session, s3_key=s3_key).update(
                    status="failed",
                    error_message=failure.get("error", "Failed to generate presigned URL"),
                )
        if upload_session and not result.get("success", False):
            upload_session.status = "failed"
            upload_session.completed_at = timezone.now()
            upload_session.save(update_fields=["status", "completed_at"])
        
        if result["success"]:
            logger.info("Successfully generated presigned URLs", extra={"total_urls": result['total_urls']})
            if upload_session:
                upload_session.status = "in_progress"
                upload_session.save(update_fields=["status"])
            
            # Ensure the response includes the full presigned post data including s3_key
            return JsonResponse({
                "success": True,
                "presigned_posts": result["presigned_posts"],
                "total_urls": result["total_urls"],
                "total_failures": result.get("total_failures", 0),
                "failures": result.get("failures", []),
                "upload_session_id": str(upload_session.id) if upload_session else None,
            })
        else:
            error_message = f"Failed to generate presigned URLs: {result.get('error', 'Unknown error')}"
            logger.error("Failed to generate presigned URLs", extra={"error": result.get('error', 'Unknown error')})
            return JsonResponse({"success": False, "error": error_message, "failures": result.get("failures", [])})
    except Exception as service_error:
        # Handle service call errors
        error_message = f"Service error: {str(service_error)}"
        logger.error("Service error generating presigned URLs", extra={"error": str(service_error)})
        return JsonResponse({"success": False, "error": error_message})


@manager_or_archivist_required
def mark_uploads_complete(request):
    """
    Mark uploads as complete and verify the files in S3.
    
    This view is called by the client after all uploads are complete to verify
    that the files were successfully uploaded to S3.
    
    This view directly uses the UploadService to verify uploaded files.
    If upload_session_id is provided, per-file audit records are updated.
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
        upload_session_id = data.get("upload_session_id")
        bucket_name = data.get("bucket_name")
        
        logger.info("Received verification request", extra={"content_type": request.content_type})
        logger.info("S3 keys to verify", extra={"count": len(s3_keys)})
        
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "Invalid JSON"})
    
    if not s3_keys:
        logger.warning("No S3 keys provided in mark_uploads_complete request")
        return JsonResponse({"success": False, "error": "No S3 keys provided"})

    access_error = _ensure_collection_access(request, s3_keys=s3_keys)
    if access_error:
        return access_error
    
    logger.info("Verifying %s uploaded files", len(s3_keys))

    try:
        upload_session = None
        if upload_session_id:
            try:
                upload_session = UploadSession.objects.get(id=upload_session_id)
                if upload_session.bucket_name:
                    bucket_name = upload_session.bucket_name
            except UploadSession.DoesNotExist:
                logger.warning("UploadSession %s not found for verification.", upload_session_id)

        verification_service = UploadVerificationService(
            upload_service=get_upload_service(),
        )
        result = verification_service.verify_keys(
            s3_keys,
            upload_session=upload_session,
            bucket_name=bucket_name,
        )

        return JsonResponse(result)
    
    except Exception as service_error:
        # Handle service call errors
        error_message = f"Failed to verify uploads: {str(service_error)}"
        logger.error("Failed to verify uploads", extra={"error": str(service_error)})
        return JsonResponse({
            "success": False,
            "error": error_message,
            "total_verified": 0,
            "total_failed": len(s3_keys)
        })


# ----- Multipart Upload Views -----

@manager_or_archivist_required
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
        bucket_name = data.get("bucket_name")
        file_size = data.get("file_size")
        
        # Validate required fields
        if not file_name or not file_type:
            error_message = "File name and type are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})

        access_error = _ensure_collection_access(request, path_hint=path_prefix or "")
        if access_error:
            return access_error
        
        logger.info("Initializing multipart upload", extra={"file_name": file_name})
        
        # Use the upload service to initialize the multipart upload
        upload_service = get_upload_service()
        result = upload_service.initialize_multipart_upload(
            file_name=file_name,
            file_type=file_type,
            path_prefix=path_prefix,
            bucket_name=bucket_name,
            file_size=int(file_size) if file_size else None,
        )
        
        if result["success"]:
            logger.info("Multipart upload initialized", extra={"upload_id": result['upload_id']})
            return JsonResponse(result)
        else:
            logger.error("Failed to initialize multipart upload", extra={"error": result.get('error')})
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error initializing multipart upload: {str(e)}"
        logger.error("Error initializing multipart upload", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})


@manager_or_archivist_required
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
        bucket_name = data.get("bucket_name")
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
        
        access_error = _ensure_collection_access(request, path_hint=s3_key)
        if access_error:
            return access_error

        logger.info("Generating part upload URLs", extra={"part_count": part_count, "s3_key": s3_key})
        
        # Use the upload service to get presigned URLs for each part
        upload_service = get_upload_service()
        result = upload_service.get_upload_part_urls(
            s3_key=s3_key,
            upload_id=upload_id,
            part_count=part_count,
            expiration=expiration,
            bucket_name=bucket_name,
        )
        
        if result["success"]:
            logger.info("Generated part upload URLs", extra={"count": len(result['presigned_urls'])})
            return JsonResponse(result)
        else:
            logger.error("Failed to generate part upload URLs", extra={"error": result.get('error')})
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error generating part upload URLs: {str(e)}"
        logger.error("Error generating part upload URLs", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})


@manager_or_archivist_required
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
        bucket_name = data.get("bucket_name")
        
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
        
        access_error = _ensure_collection_access(request, path_hint=s3_key)
        if access_error:
            return access_error

        logger.info("Completing multipart upload", extra={"s3_key": s3_key, "parts_count": len(parts)})
        
        # Use the upload service to complete the multipart upload
        upload_service = get_upload_service()
        result = upload_service.complete_multipart_upload(
            s3_key=s3_key,
            upload_id=upload_id,
            parts=parts,
            bucket_name=bucket_name,
        )
        
        if result["success"]:
            logger.info("Multipart upload completed", extra={"s3_key": s3_key})
            return JsonResponse(result)
        else:
            logger.error("Failed to complete multipart upload", extra={"error": result.get('error')})
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error completing multipart upload: {str(e)}"
        logger.error("Error completing multipart upload", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})


@manager_or_archivist_required
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
        bucket_name = data.get("bucket_name")
        
        # Validate required fields
        if not s3_key or not upload_id:
            error_message = "S3 key and upload ID are required"
            logger.warning(error_message)
            return JsonResponse({"success": False, "error": error_message})
        
        access_error = _ensure_collection_access(request, path_hint=s3_key)
        if access_error:
            return access_error

        logger.info("Aborting multipart upload", extra={"s3_key": s3_key})
        
        # Use the upload service to abort the multipart upload
        upload_service = get_upload_service()
        result = upload_service.abort_multipart_upload(
            s3_key=s3_key,
            upload_id=upload_id,
            bucket_name=bucket_name,
        )
        
        if result["success"]:
            logger.info("Multipart upload aborted", extra={"s3_key": s3_key})
            return JsonResponse(result)
        else:
            logger.error("Failed to abort multipart upload", extra={"error": result.get('error')})
            return JsonResponse(result)
    
    except json.JSONDecodeError:
        error_message = "Invalid JSON data"
        logger.warning(error_message)
        return JsonResponse({"success": False, "error": error_message})
    
    except Exception as e:
        error_message = f"Error aborting multipart upload: {str(e)}"
        logger.error("Error aborting multipart upload", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})


@archivist_required
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
            logger.info("Found in-progress multipart uploads", extra={"count": result.get('count', 0)})
            return JsonResponse(result)
        else:
            logger.error("Failed to list multipart uploads", extra={"error": result.get('error')})
            return JsonResponse(result)
    
    except Exception as e:
        error_message = f"Error listing multipart uploads: {str(e)}"
        logger.error("Error listing multipart uploads", extra={"error": str(e)})
        return JsonResponse({"success": False, "error": error_message})
