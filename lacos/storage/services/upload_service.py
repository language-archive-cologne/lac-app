import logging
import time
import os
from typing import Dict, Any, List, Tuple, Set, Optional

import boto3

from .base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)

class UploadService(BaseStorageService):
    """
    Service for handling file uploads to S3/MinIO buckets.
    
    This service focuses on core S3 operations for uploads, completely independent of
    web frameworks or HTTP concepts. It provides pure business logic that can be used
    by any presentation layer (REST API, web UI, CLI, etc).
    
    The service implements the presigned URL pattern for browser-to-S3 direct uploads,
    allowing clients to upload directly to S3 without server intermediation.
    """
    
    def __init__(self):
        """Initialize the UploadService with base storage configuration."""
        super().__init__()
        logger.info("UploadService initialized")

    def _generate_file_key(self, file_name: str, path_prefix: Optional[str] = None) -> str:
        """
        Generate a clean S3 key (path) for a file.
        
        Args:
            file_name (str): The name of the file
            path_prefix (str, optional): Path prefix to prepend to the file name
            
        Returns:
            str: The generated S3 key
        """
        # Sanitize the file name to work with S3 (replace spaces with underscores)
        clean_file_name = file_name.replace(' ', '_')
        
        # Build the full S3 key (path)
        if path_prefix:
            # Ensure the path has no leading or trailing slashes
            clean_prefix = path_prefix.strip('/')
            if clean_prefix:
                return f"{clean_prefix}/{clean_file_name}"
        
        # Just return the clean file name if no prefix
        return clean_file_name

    def generate_presigned_post(self, file_name: str, file_type: str, path_prefix: Optional[str] = None, 
                             expiration: int = 3600) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct upload to S3.
        
        Args:
            file_name: The name of the file to upload
            file_type: The MIME type of the file
            path_prefix: Optional prefix for the S3 key
            expiration: Expiration time in seconds
            
        Returns:
            Dictionary with presigned post data
        """
        try:
            # Generate a unique key for the file
            file_key = self._generate_file_key(file_name, path_prefix)
            
            logger.info(f"Generating presigned upload URL for {file_key}")
            
            # Use the presigned client if available, otherwise use the regular client
            client = getattr(self, 'presigned_client', self.s3_client)
            
            # Generate the presigned POST data
            presigned_post = client.generate_presigned_post(
                Bucket=self.ingest_bucket,
                Key=file_key,
                Fields={
                    'Content-Type': file_type
                },
                Conditions=[
                    {'Content-Type': file_type}
                ],
                ExpiresIn=expiration
            )
            
            # Log detailed information about the generated URL for debugging
            logger.info(f"Generated presigned URL: {presigned_post['url']}")
            logger.info(f"Generated presigned fields: {presigned_post['fields']}")
            
            # For easier browser debugging, include formatted examples
            curl_example = self._format_curl_example(presigned_post, file_name, file_type)
            logger.debug(f"Example curl command: {curl_example}")
            
            # Return a standardized structure matching what the client expects
            return {
                'success': True,
                'file_name': file_name,
                'file_type': file_type,
                's3_key': file_key,
                'url': presigned_post['url'],
                'fields': presigned_post['fields']
            }
        except Exception as e:
            logger.error(f"Error generating presigned POST for {file_name}: {str(e)}")
            logger.exception(e)  # Log the full exception with traceback
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }
    
    def _format_curl_example(self, presigned_post: Dict[str, Any], file_name: str, file_type: str) -> str:
        """
        Format a curl command example for testing the presigned URL.
        
        Args:
            presigned_post: The presigned post data from boto3
            file_name: The name of the file
            file_type: The MIME type of the file
            
        Returns:
            str: A curl command that can be used to test the upload
        """
        # Start building the curl command
        curl_cmd = ['curl -v']
        
        # Add the URL
        curl_cmd.append(f"-X POST '{presigned_post['url']}'")
        
        # Add all the fields
        for key, value in presigned_post['fields'].items():
            curl_cmd.append(f"-F '{key}={value}'")
        
        # Add the file field
        curl_cmd.append(f"-F 'file=@/path/to/{file_name};type={file_type}'")
        
        # Join everything together
        return " \\\n  ".join(curl_cmd)
    
    def generate_batch_presigned_posts(self, files_metadata: List[Dict[str, str]], 
                                    path_prefix: Optional[str] = None,
                                    expiration: int = 3600) -> Dict[str, Any]:
        """
        Generate multiple presigned URLs for direct upload to S3.
        
        Args:
            files_metadata (List[Dict[str, str]]): List of dictionaries with file_name and file_type for each file.
                           May include 'path' to specify a file-specific path.
            path_prefix (str, optional): Folder path to prepend to all file paths
            expiration (int): Time in seconds for the URLs to be valid (default 1 hour)
            
        Returns:
            Dict[str, Any]: Dictionary containing the presigned URL data for all files or error information
        """
        results = []
        failures = []
        
        for file_meta in files_metadata:
            file_name = file_meta.get('file_name')
            file_type = file_meta.get('file_type')
            file_path = file_meta.get('path')  # Get the optional file-specific path
            
            if not file_name or not file_type:
                logger.warning(f"Skipping invalid file metadata: {file_meta}")
                failures.append({
                    'file_meta': file_meta,
                    'error': 'Missing file_name or file_type'
                })
                continue
            
            # Create effective path prefix by combining the overall prefix with file-specific path
            effective_path_prefix = path_prefix
            if file_path:
                if effective_path_prefix:
                    effective_path_prefix = f"{effective_path_prefix}/{file_path}"
                else:
                    effective_path_prefix = file_path
            
            # Generate the presigned post for this file
            result = self.generate_presigned_post(
                file_name=file_name,
                file_type=file_type,
                path_prefix=effective_path_prefix,
                expiration=expiration
            )
            
            if result['success']:
                results.append(result)
            else:
                failures.append({
                    'file_meta': file_meta,
                    'error': result.get('error', 'Unknown error')
                })
        
        return {
            'success': len(failures) == 0,
            'presigned_posts': results,
            'failures': failures,
            'total_urls': len(results),
            'total_failures': len(failures)
        }
    
    def get_upload_url_with_acceleration(self, file_name: str, file_type: str, 
                                      path_prefix: Optional[str] = None,
                                      expiration: int = 3600) -> Dict[str, Any]:
        """
        Generate a presigned URL with S3 Transfer Acceleration for maximum upload speed.
        
        Args:
            file_name (str): Name of the file to upload
            file_type (str): MIME type of the file
            path_prefix (str, optional): Folder path to prepend to the file name
            expiration (int): Time in seconds for the URL to be valid (default 1 hour)
            
        Returns:
            Dict[str, Any]: Dictionary containing the presigned URL data with acceleration enabled or error information
        """
        try:
            # Sanitize the file name to work with S3
            clean_file_name = file_name.replace(' ', '_')
            
            # Build the full S3 key (path)
            s3_key = clean_file_name
            if path_prefix:
                # Ensure the path has a trailing slash but no leading slash
                path_prefix = path_prefix.strip('/')
                if path_prefix:
                    s3_key = f"{path_prefix}/{clean_file_name}"
            
            logger.info(f"Generating accelerated upload URL for {s3_key}")
            
            # Create a special client with acceleration enabled
            s3_client_accelerated = boto3.client(
                's3',
                region_name=self.region,
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=boto3.session.Config(s3={'use_accelerate_endpoint': True})
            )
            
            # Generate the presigned post data with acceleration
            presigned_post = s3_client_accelerated.generate_presigned_post(
                Bucket=self.ingest_bucket,
                Key=s3_key,
                Fields={
                    'Content-Type': file_type
                },
                Conditions=[
                    {'Content-Type': file_type}
                ],
                ExpiresIn=expiration
            )
            
            return {
                'success': True,
                'file_name': file_name,
                's3_key': s3_key,
                'url': presigned_post['url'],
                'fields': presigned_post['fields'],
                'expires_in': expiration,
                'acceleration_enabled': True
            }
            
        except Exception as e:
            logger.error(f"Error generating accelerated upload URL for {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }
    
    def mark_upload_complete(self, s3_key: str) -> Dict[str, Any]:
        """
        Mark an S3 upload as complete and verify the file exists.
        
        Args:
            s3_key (str): The S3 key for the uploaded file
            
        Returns:
            Dict[str, Any]: Dictionary containing verification information or error information
        """
        try:
            # Check if the file exists in S3
            response = self.s3_client.head_object(
                Bucket=self.ingest_bucket,
                Key=s3_key
            )
            
            file_size = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'application/octet-stream')
            last_modified = response.get('LastModified', None)
            
            return {
                'success': True,
                's3_key': s3_key,
                'exists': True,
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size),
                'content_type': content_type,
                'last_modified': last_modified.isoformat() if last_modified else None
            }
            
        except Exception as e:
            logger.error(f"Error verifying uploaded file {s3_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                's3_key': s3_key,
                'exists': False
            }
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB" 