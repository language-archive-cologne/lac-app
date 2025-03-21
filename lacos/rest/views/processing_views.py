from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import status
import logging
import json
import os

from lacos.storage.services.upload_service import UploadService

logger = logging.getLogger(__name__)

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

@api_view(['POST'])
@permission_classes([AllowAny])
def upload_error(request):
    """
    Log upload errors from the client.
    
    Request should include:
    - file_name: Name of the file that failed
    - s3_key: S3 key of the file (if available)
    - error: Error message or details
    
    Returns:
        A Response object acknowledging the error report
    """
    data = request.data
    
    # Extract error details
    file_name = data.get('file_name', 'unknown')
    s3_key = data.get('s3_key', 'unknown')
    error_message = data.get('error', 'No error details provided')
    
    # Log the error
    logger.error(f"Client reported upload error for file '{file_name}' (S3 key: {s3_key}): {error_message}")
    
    # You could also store these errors in the database if needed
    
    return Response({
        'success': True,
        'message': 'Error logged successfully'
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_upload_complete(request):
    """
    Mark an upload as complete and trigger processing of the uploaded files.
    
    This endpoint is called after files have been uploaded to S3 to trigger
    any necessary processing (like importing data from XML files).
    
    Expected POST parameters:
    - folder_name: The folder name in S3 where files were uploaded
    - uploaded_files: Array of objects with s3_key and file_name properties
    """
    try:
        # Get the uploaded files information
        folder_name = request.data.get('folder_name')
        uploaded_files = request.data.get('uploaded_files')
        
        if not folder_name or not uploaded_files:
            logger.warning("Missing required parameters for marking upload complete")
            return Response({
                'success': False,
                'error': 'Missing required parameters: folder_name and uploaded_files'
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
            'folder_name': folder_name,
            'successful': len(processed_files)  # Added for frontend compatibility
        })
    
    except Exception as e:
        logger.exception(f"Error in mark_upload_complete: {str(e)}")
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 