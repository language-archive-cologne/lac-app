from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status


from lacos.storage.services.upload_service import UploadService

import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def get_upload_url(request):
    """
    Generate a presigned URL for direct upload to S3.
    
    Request should include:
    - file_name: Name of the file
    - file_type: MIME type of the file
    - folder_name: (optional) Folder to place the file in
    
    Returns:
        A Response object with presigned URL information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    file_name = data.get('file_name')
    file_type = data.get('file_type')
    folder_name = data.get('folder_name')
    
    # Validate required parameters
    if not file_name or not file_type:
        logger.warning("Missing required parameters for presigned URL generation")
        return Response(
            {"success": False, "error": "Missing required parameters: file_name and file_type are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Call service layer
    service = UploadService()
    result = service.generate_presigned_post(
        file_name=file_name,
        file_type=file_type,
        path_prefix=folder_name
    )
    
    # Handle service result and return appropriate HTTP response
    if result.get('success') is False:
        logger.error(f"Failed to generate presigned URL: {result.get('error')}")
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    logger.info(f"Successfully generated presigned URL for {file_name}")
    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def get_batch_upload_urls(request):
    """
    Generate presigned URLs for multiple files in one request.
    
    Request should include:
    - files: List of file metadata objects with file_name and file_type
    - folder_name: (optional) Common folder for all files
    - expiration: (optional) Expiration time in seconds
    
    Returns:
        A Response object with batch presigned URL information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    files = data.get('files', [])
    folder_name = data.get('folder_name')
    expiration = data.get('expiration', 3600)  # 1 hour default
    
    # Validate required parameters
    if not files or not isinstance(files, list):
        logger.warning("Missing or invalid 'files' parameter for batch URL generation")
        return Response(
            {"success": False, "error": "Missing or invalid 'files' parameter. Expected a list of file metadata."},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Call service layer
    service = UploadService()
    result = service.generate_batch_presigned_posts(
        files_metadata=files,
        path_prefix=folder_name,
        expiration=expiration
    )
    
    # Handle service result and return appropriate HTTP response
    if result.get('total_urls', 0) == 0:
        logger.warning(f"No valid presigned URLs generated from {len(files)} files")
        # Return a 207 Multi-Status if some URLs were generated but others failed
        if result.get('total_failures', 0) > 0:
            return Response(result, status=status.HTTP_207_MULTI_STATUS)
            
    if result.get('success') is False:
        logger.error(f"Failed to generate batch presigned URLs: {len(result.get('failures', []))} failures")
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    logger.info(f"Successfully generated {result.get('total_urls', 0)} presigned URLs")
    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def get_accelerated_upload_url(request):
    """
    Generate a presigned URL with S3 Transfer Acceleration for maximum upload speed.
    
    Request should include:
    - file_name: Name of the file
    - file_type: MIME type of the file
    - folder_name: (optional) Folder to place the file in
    
    Returns:
        A Response object with accelerated presigned URL information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    file_name = data.get('file_name')
    file_type = data.get('file_type')
    folder_name = data.get('folder_name')
    
    # Validate required parameters
    if not file_name or not file_type:
        logger.warning("Missing required parameters for accelerated presigned URL generation")
        return Response(
            {"success": False, "error": "Missing required parameters: file_name and file_type are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Call service layer
    service = UploadService()
    result = service.get_upload_url_with_acceleration(
        file_name=file_name,
        file_type=file_type,
        path_prefix=folder_name
    )
    
    # Handle service result and return appropriate HTTP response
    if result.get('success') is False:
        logger.error(f"Failed to generate accelerated presigned URL: {result.get('error')}")
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    logger.info(f"Successfully generated accelerated presigned URL for {file_name}")
    return Response(result)


@api_view(['POST'])
@permission_classes([AllowAny])
def mark_upload_complete(request):
    """
    Mark an S3 upload as complete and verify the file exists.
    
    Request should include:
    - s3_key: The S3 key for the uploaded file
    
    Returns:
        A Response object with file verification information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    s3_key = data.get('s3_key')
    
    # Validate required parameters
    if not s3_key:
        logger.warning("Missing required s3_key parameter for marking upload complete")
        return Response(
            {"success": False, "error": "Missing required parameter: s3_key"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Call service layer
    service = UploadService()
    result = service.mark_upload_complete(s3_key)
    
    # Handle service result and return appropriate HTTP response
    if result.get('success') is False:
        logger.error(f"Failed to verify upload for {s3_key}: {result.get('error')}")
        return Response(result, status=status.HTTP_404_NOT_FOUND)
    
    logger.info(f"Successfully verified uploaded file: {s3_key}")
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def copy_object(request):
    """
    Copy an object from one location to another within S3.
    
    Request should include:
    - source_key: Source object key (path)
    - dest_key: Destination object key (path)
    - source_bucket: (optional) Source bucket name
    - dest_bucket: (optional) Destination bucket name
    
    Returns:
        A Response object with copy operation information and status code
    """
    data = request.data
    
    # Extract and validate parameters
    source_key = data.get('source_key')
    dest_key = data.get('dest_key')
    source_bucket = data.get('source_bucket')
    dest_bucket = data.get('dest_bucket')
    
    # Validate required parameters
    if not source_key or not dest_key:
        logger.warning("Missing required parameters for copying object")
        return Response(
            {"success": False, "error": "Missing required parameters: source_key and dest_key are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Call service layer
    service = UploadService()
    result = service.copy_object(
        source_key=source_key,
        dest_key=dest_key,
        source_bucket=source_bucket,
        dest_bucket=dest_bucket
    )
    
    # Handle service result and return appropriate HTTP response
    if result.get('success') is False:
        logger.error(f"Failed to copy object from {source_key} to {dest_key}: {result.get('error')}")
        return Response(result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    logger.info(f"Successfully copied object from {source_key} to {dest_key}")
    return Response(result)
