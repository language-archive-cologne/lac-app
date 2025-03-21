from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json
import os

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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_uploaded_files(request):
    """
    Process files that have been successfully uploaded to S3.
    
    This endpoint is called after files have been uploaded to S3 to trigger
    any necessary processing (like importing data from XML files).
    
    Expected POST parameters:
    - folder_name: The folder name in S3 where files were uploaded
    - uploaded_files: JSON array of objects with s3_key and file_name properties
    """
    try:
        # Get the uploaded files information
        folder_name = request.data.get('folder_name')
        uploaded_files_json = request.data.get('uploaded_files')
        
        if not folder_name or not uploaded_files_json:
            logger.warning("Missing required parameters for processing uploaded files")
            return Response({
                'success': False,
                'error': 'Missing required parameters: folder_name and uploaded_files'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse the uploaded files JSON
        try:
            uploaded_files = json.loads(uploaded_files_json) if isinstance(uploaded_files_json, str) else uploaded_files_json
        except json.JSONDecodeError:
            logger.warning("Invalid uploaded_files JSON format")
            return Response({
                'success': False,
                'error': 'Invalid uploaded_files JSON format'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process each file based on its type
        processed_files = []
        failed_files = []
        
        for file_info in uploaded_files:
            s3_key = file_info.get('s3_key')
            file_name = file_info.get('file_name')
            
            if not s3_key:
                failed_files.append({
                    'file_name': file_name,
                    'error': 'Missing S3 key'
                })
                continue
            
            # Check if the file exists in S3
            upload_service = UploadService()
            if not upload_service.check_file_exists(s3_key):
                failed_files.append({
                    'file_name': file_name,
                    's3_key': s3_key,
                    'error': 'File not found in S3'
                })
                continue
            
            # Process the file based on its extension
            _, ext = os.path.splitext(file_name)
            ext = ext.lower()
            
            try:
                # Example: Process XML files
                if ext == '.xml':
                    # Get the file content
                    file_content = upload_service.get_object_content(s3_key)
                    
                    # Process the XML content (implement your specific logic here)
                    # For example, you might call your bundle importer
                    # result = process_xml_file(file_content)
                    
                    processed_files.append({
                        'file_name': file_name,
                        's3_key': s3_key,
                        'status': 'Processed as XML'
                    })
                
                # Add more file type handlers as needed
                else:
                    # For other file types, just mark as stored
                    processed_files.append({
                        'file_name': file_name,
                        's3_key': s3_key,
                        'status': 'Stored in S3'
                    })
            
            except Exception as e:
                logger.exception(f"Error processing file {file_name}: {str(e)}")
                failed_files.append({
                    'file_name': file_name,
                    's3_key': s3_key,
                    'error': str(e)
                })
        
        # Return the processing results
        return Response({
            'success': len(processed_files) > 0,
            'processed_files': processed_files,
            'failed_files': failed_files,
            'folder_name': folder_name
        })
    
    except Exception as e:
        logger.exception(f"Error in process_uploaded_files: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
