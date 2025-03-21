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
    """
    
    def __init__(self):
        """Initialize the UploadService with base storage configuration."""
        super().__init__()
        logger.info("UploadService initialized")

    def generate_presigned_post(self, file_name: str, file_type: str, path_prefix: Optional[str] = None, 
                             expiration: int = 3600) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct upload to S3.
        
        Args:
            file_name (str): Name of the file to upload
            file_type (str): MIME type of the file
            path_prefix (str, optional): Folder path to prepend to the file name
            expiration (int): Time in seconds for the URL to be valid (default 1 hour)
            
        Returns:
            Dict[str, Any]: Dictionary containing the presigned URL data or error information
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
            
            logger.info(f"Generating presigned upload URL for {s3_key}")
            
            # Generate the presigned post data
            presigned_post = self.s3_client.generate_presigned_post(
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
                'expires_in': expiration
            }
            
        except Exception as e:
            logger.error(f"Error generating presigned post for {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }
    
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
    
    def copy_object(self, source_key: str, dest_key: str, 
                 source_bucket: Optional[str] = None, 
                 dest_bucket: Optional[str] = None) -> Dict[str, Any]:
        """
        Copy an object from one location to another within S3.
        
        Args:
            source_key (str): Source object key (path)
            dest_key (str): Destination object key (path)
            source_bucket (str, optional): Source bucket name (defaults to ingest bucket)
            dest_bucket (str, optional): Destination bucket name (defaults to production bucket)
            
        Returns:
            Dict[str, Any]: Dictionary with copy information or error information
        """
        source_bucket = source_bucket or self.ingest_bucket
        dest_bucket = dest_bucket or self.production_bucket
        
        try:
            logger.info(f"Copying object from {source_bucket}/{source_key} to {dest_bucket}/{dest_key}")
            
            copy_source = {'Bucket': source_bucket, 'Key': source_key}
            response = self.s3_client.copy_object(
                CopySource=copy_source,
                Bucket=dest_bucket,
                Key=dest_key
            )
            
            return {
                'success': True,
                'source_key': source_key,
                'dest_key': dest_key,
                'source_bucket': source_bucket,
                'dest_bucket': dest_bucket,
                'copy_time': response.get('CopyObjectResult', {}).get('LastModified', 'Unknown')
            }
            
        except Exception as e:
            logger.error(f"Error copying object {source_key} to {dest_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'source_key': source_key,
                'dest_key': dest_key
            }
    
    def upload_folder_to_bucket(self, local_folder_path: str, bucket_name: str = None, target_prefix: str = "") -> Dict[str, Any]:
        """
        Upload a local folder and all its contents to the specified S3 bucket.
        
        Args:
            local_folder_path (str): The local path to the folder to upload
            bucket_name (str, optional): The name of the bucket to upload to 
            target_prefix (str, optional): The prefix (path) in the bucket where the folder should be uploaded
            
        Returns:
            Dict[str, Any]: Dictionary containing the upload results
        """
        if bucket_name is None:
            bucket_name = self.ingest_bucket
            
        if not os.path.exists(local_folder_path):
            return {"success": False, "error": f"Local folder does not exist: {local_folder_path}"}
            
        if not os.path.isdir(local_folder_path):
            return {"success": False, "error": f"Path is not a directory: {local_folder_path}"}
        
        try:
            uploaded_files = []
            failed_files = []
            total_size = 0
            
            # Get the base folder name
            base_folder_name = os.path.basename(os.path.normpath(local_folder_path))
            
            # Create the target prefix including the base folder name
            if target_prefix:
                full_prefix = f"{target_prefix.rstrip('/')}/{base_folder_name}/"
            else:
                full_prefix = f"{base_folder_name}/"
                
            logger.info(f"Uploading folder {local_folder_path} to {bucket_name} with prefix {full_prefix}")
            
            # Walk through the directory and upload all files
            for root, dirs, files in os.walk(local_folder_path):
                # Calculate the relative path from the local_folder_path
                relative_path = os.path.relpath(root, local_folder_path)
                
                # Skip the root directory itself
                if relative_path == ".":
                    s3_prefix = full_prefix
                else:
                    s3_prefix = f"{full_prefix}{relative_path}/"
                
                # Upload each file in the current directory
                for file in files:
                    local_file_path = os.path.join(root, file)
                    s3_key = f"{s3_prefix}{file}"
                    
                    try:
                        # Get file size for reporting
                        file_size = os.path.getsize(local_file_path)
                        total_size += file_size
                        
                        # Upload the file
                        self.s3_client.upload_file(local_file_path, bucket_name, s3_key)
                        uploaded_files.append({
                            "local_path": local_file_path,
                            "s3_key": s3_key,
                            "size": file_size
                        })
                        logger.info(f"Uploaded {local_file_path} to {s3_key}")
                    except Exception as e:
                        logger.error(f"Failed to upload {local_file_path}: {str(e)}")
                        failed_files.append({
                            "local_path": local_file_path,
                            "error": str(e)
                        })
            
            return {
                "success": True,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "failed_count": len(failed_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "target_prefix": full_prefix
            }
            
        except Exception as e:
            logger.error(f"Error uploading folder {local_folder_path} to bucket {bucket_name}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def upload_files_directly(self, files, folder_name: str, bucket_name: str = None, file_paths: dict = None) -> Dict[str, Any]:
        """
        Upload files directly from a request to S3.
        
        Args:
            files: List of files to upload (Django InMemoryUploadedFile or similar)
            folder_name (str): The folder name to use as prefix
            bucket_name (str, optional): The target bucket name
            file_paths (dict, optional): Dictionary mapping file names to custom S3 paths
            
        Returns:
            Dict[str, Any]: Dictionary containing the upload results
        """
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        
        try:
            uploaded_files = []
            failed_files = []
            total_size = 0
            
            # Process each file
            for f in files:
                file_name = f.name
                content_type = getattr(f, 'content_type', 'application/octet-stream')
                
                # Determine the S3 key (path)
                if file_paths and file_name in file_paths:
                    # Use the custom path if provided
                    s3_key = file_paths[file_name]
                else:
                    # Otherwise construct a path with the folder name
                    s3_key = f"{folder_name}/{file_name}"
                
                try:
                    # Upload the file
                    self.s3_client.upload_fileobj(
                        f, 
                        bucket_name, 
                        s3_key,
                        ExtraArgs={'ContentType': content_type}
                    )
                    
                    # Get the file size
                    file_size = f.size if hasattr(f, 'size') else 0
                    total_size += file_size
                    
                    uploaded_files.append({
                        "file_name": file_name,
                        "s3_key": s3_key,
                        "size": file_size,
                        "content_type": content_type
                    })
                    logger.info(f"Directly uploaded {file_name} to {s3_key}")
                
                except Exception as e:
                    logger.error(f"Failed to directly upload {file_name}: {str(e)}")
                    failed_files.append({
                        "file_name": file_name,
                        "error": str(e)
                    })
            
            return {
                "success": len(failed_files) == 0,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "failed_count": len(failed_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "folder_name": folder_name
            }
            
        except Exception as e:
            logger.error(f"Error directly uploading files to {bucket_name}/{folder_name}: {str(e)}")
            return {"success": False, "error": str(e)}
        
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB" 