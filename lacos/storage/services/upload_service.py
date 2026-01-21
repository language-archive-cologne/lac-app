import logging
import time
import os
import json
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
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(UploadService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the UploadService with base storage configuration.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        logger.info("UploadService initialized")
        self.initialized = True

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
                             expiration: int = 3600, file_size: int = 0, bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a presigned URL for direct upload to S3.
        Auto-detects if multipart is needed based on file size.

        Args:
            file_name: The name of the file to upload
            file_type: The MIME type of the file
            path_prefix: Optional prefix for the S3 key
            expiration: Expiration time in seconds
            file_size: Size of the file in bytes (for auto multipart detection)

        Returns:
            Dictionary with presigned post data
        """
        try:
            # Generate a unique key for the file
            file_key = self._generate_file_key(file_name, path_prefix)

            logger.info(f"Generating presigned upload URL for {file_key}")

            # Check if multipart is needed based on file size
            threshold = self._get_multipart_threshold()
            size_for_parts = file_size if file_size > 0 else threshold + 1
            parts_info = self.calculate_multipart_parts(size_for_parts)

            if parts_info['should_use_multipart'] or file_size <= 0:
                    logger.info(f"File size {file_size} exceeds threshold, using multipart upload")

                    # Initialize multipart upload
                    init_result = self.initialize_multipart_upload(
                        file_name=file_name,
                        file_type=file_type,
                        path_prefix=path_prefix,
                        bucket_name=bucket_name
                    )

                    if init_result['success']:
                        return {
                            'success': True,
                            'file_name': file_name,
                            's3_key': init_result['s3_key'],
                            'file_type': file_type,
                            'upload_type': 'multipart',
                            'upload_id': init_result['upload_id'],
                            'parts_info': parts_info,
                            'expires_in': expiration,
                            'bucket_name': init_result.get('bucket_name')
                        }

            # Single-part upload for smaller files or when multipart is not needed
            # Use the presigned client if available, otherwise use the regular client
            client = getattr(self, 'presigned_client', self.s3_client)

            # Use provided bucket or fall back to default ingest bucket
            target_bucket = bucket_name or self.ingest_bucket

            # Generate the presigned POST data
            presigned_post = client.generate_presigned_post(
                Bucket=target_bucket,
                Key=file_key,
                Fields={
                    'Content-Type': file_type
                },
                Conditions=[
                    {'Content-Type': file_type}
                ],
                ExpiresIn=expiration
            )
            
            # Log the generated URL for debugging
            logger.info(f"Generated presigned URL: {presigned_post['url']}")
            logger.info(f"Generated presigned fields: {json.dumps(presigned_post['fields'])}")
            
            return {
                'success': True,
                'presigned_post': presigned_post,
                's3_key': file_key,
                'file_name': file_name,
                'file_type': file_type,
                'upload_type': 'single',
                'expires_in': expiration,
                'bucket_name': target_bucket
            }
        except Exception as e:
            logger.error(f"Error generating presigned POST for {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
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
    
    def generate_batch_presigned_posts(
        self,
        files_metadata: List[Dict[str, Any]],
        path_prefix: Optional[str] = None,
        expiration: int = 3600,
        bucket_name: Optional[str] = None,
        file_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate multiple presigned URLs for direct upload to S3.
        Auto-detects multipart needs based on file size.

        Args:
            files_metadata (List[Dict[str, str]]): List of dictionaries with file_name, file_type, and optionally file_size.
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
            # Note: webkitRelativePath includes the filename, so we need to strip it
            effective_path_prefix = path_prefix
            if file_path:
                # Strip the filename from the path if it ends with the filename
                if file_path.endswith(file_name):
                    file_path = file_path[:-len(file_name)].rstrip('/')
                if file_path:  # Only use if there's still a path after stripping
                    if effective_path_prefix:
                        effective_path_prefix = f"{effective_path_prefix}/{file_path}"
                    else:
                        effective_path_prefix = file_path
            
            # Generate the presigned post for this file
            effective_file_size = file_meta.get('file_size', file_size or 0)

            result = self.generate_presigned_post(
                file_name=file_name,
                file_type=file_type,
                path_prefix=effective_path_prefix,
                expiration=expiration,
                file_size=effective_file_size,
                bucket_name=bucket_name  # Pass bucket name
            )
            
            # Validate the result has all required fields
            if result['success']:
                # For multipart uploads, we won't have presigned_post but will have upload_id and parts_info
                if result.get('upload_type') == 'multipart':
                    if 'upload_id' not in result or 'parts_info' not in result:
                        logger.error(f"Missing multipart fields in result for {file_name}")
                        failures.append({
                            'file_meta': file_meta,
                            'error': "Missing multipart upload fields in server response"
                        })
                        continue
                else:
                    # For single uploads, validate presigned_post structure
                    if 'presigned_post' not in result:
                        logger.error(f"Missing presigned_post in result for {file_name}")
                        failures.append({
                            'file_meta': file_meta,
                            'error': "Missing presigned_post in server response"
                        })
                        continue

                    # Validate that presigned_post has url and fields
                    presigned_post = result['presigned_post']
                    if not isinstance(presigned_post, dict) or 'url' not in presigned_post or 'fields' not in presigned_post:
                        logger.error(f"Invalid presigned_post structure for {file_name}: {presigned_post}")
                        failures.append({
                            'file_meta': file_meta,
                            'error': f"Invalid presigned_post format. Keys: {list(presigned_post.keys()) if isinstance(presigned_post, dict) else 'not a dict'}"
                        })
                        continue

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
    
    def mark_upload_complete(self, s3_key: str, bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Mark an S3 upload as complete and verify the file exists.
        
        Args:
            s3_key (str): The S3 key for the uploaded file
            bucket_name (str, optional): Bucket to check (defaults to ingest bucket)
            
        Returns:
            Dict[str, Any]: Dictionary containing verification information or error information
        """
        try:
            target_bucket = bucket_name or self.ingest_bucket
            # Check if the file exists in S3
            response = self.s3_client.head_object(
                Bucket=target_bucket,
                Key=s3_key
            )
            
            file_size = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'application/octet-stream')
            last_modified = response.get('LastModified', None)
            etag = response.get('ETag', '').strip('"')
            
            return {
                'success': True,
                's3_key': s3_key,
                'exists': True,
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size),
                'content_type': content_type,
                'last_modified': last_modified.isoformat() if last_modified else None,
                'etag': etag,
                'bucket_name': target_bucket,
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
        """
        Format a size in bytes to a human-readable format.
        
        Args:
            size_bytes (int): Size in bytes
            
        Returns:
            str: Formatted size string
        """
        # Define size units
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        size = float(size_bytes)
        unit_index = 0
        
        # Find the appropriate unit
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        # Format with proper precision
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        else:
            return f"{size:.2f} {units[unit_index]}"

    def _get_multipart_threshold(self) -> int:
        """
        Resolve the multipart threshold from settings, defaulting to 5GB.
        A higher value means more uploads will use single-part.
        """
        try:
            from django.conf import settings
            cfg = getattr(settings, 'MULTIPART_UPLOAD_SETTINGS', {}) or {}
            # Default to 5GB if not configured
            return int(cfg.get('multipart_threshold', 5 * 1024 * 1024 * 1024))
        except Exception:
            return 5 * 1024 * 1024 * 1024

    def calculate_optimal_chunk_size(self, file_size: int) -> int:
        """
        Calculate optimal chunk size based on file size using dynamic sizing.

        AWS Best Practices (2024):
        - Use multipart for files > 100MB
        - Minimum part size: 5MB (except last part)
        - Maximum parts: 10,000
        - Optimal chunk sizes: 16-128MB for most use cases

        Dynamic Algorithm:
        - 100-500MB: Use 25MB chunks (4-20 parts)
        - 500MB-1GB: Use 50MB chunks (10-20 parts)
        - 1GB-5GB: Use 100MB chunks (10-50 parts)
        - 5GB-50GB: Use 250MB chunks (20-200 parts)
        - >50GB: Calculate to keep parts around 500-1000
        """
        MB = 1024 * 1024
        GB = 1024 * MB

        # Log file size for debugging
        size_mb = file_size / MB
        size_gb = file_size / GB
        if size_gb >= 1:
            logger.debug(f"Calculating multipart chunks for {size_gb:.2f}GB file")
        else:
            logger.debug(f"Calculating multipart chunks for {size_mb:.1f}MB file")

        # Optimized chunk sizes to minimize parts while maintaining performance
        if file_size <= 500 * MB:
            # 100-500MB: Use 25MB chunks (results in 4-20 parts)
            chunk_size = 25 * MB
            logger.debug(f"Using 25MB chunks for small file ({size_mb:.1f}MB)")
        elif file_size <= 1 * GB:
            # 500MB-1GB: Use 50MB chunks (results in 10-20 parts)
            chunk_size = 50 * MB
            logger.debug(f"Using 50MB chunks for medium file ({size_mb:.1f}MB)")
        elif file_size <= 5 * GB:
            # 1GB-5GB: Use 100MB chunks (results in 10-50 parts)
            chunk_size = 100 * MB
            logger.debug(f"Using 100MB chunks for large file ({size_gb:.2f}GB)")
        elif file_size <= 50 * GB:
            # 5GB-50GB: Use 250MB chunks (results in 20-200 parts)
            chunk_size = 250 * MB
            logger.debug(f"Using 250MB chunks for very large file ({size_gb:.2f}GB)")
        else:
            # >50GB: Calculate to keep parts around 500-1000
            target_parts = 750  # Aim for middle of range
            chunk_size = (file_size + target_parts - 1) // target_parts
            # Round up to nearest 50MB for consistency
            chunk_size = ((chunk_size + (50 * MB) - 1) // (50 * MB)) * (50 * MB)
            logger.debug(f"Using dynamic {chunk_size/MB:.0f}MB chunks for huge file ({size_gb:.2f}GB)")

        return chunk_size

    def calculate_multipart_parts(self, file_size: int, chunk_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate optimal multipart upload parameters using dynamic sizing.

        Args:
            file_size: Size of the file in bytes
            chunk_size: Desired chunk size in bytes (optional, overrides dynamic sizing)

        Returns:
            Dict with multipart calculation results
        """
        # S3 limits for multipart uploads
        min_part_size = 5 * 1024 * 1024  # 5MB minimum
        max_parts = 10000  # Maximum number of parts

        # If chunk_size not provided, try to get it from settings first, then fall back to intelligent dynamic sizing
        if chunk_size is None:
            try:
                from django.conf import settings
                configured_chunk = int(settings.MULTIPART_UPLOAD_SETTINGS.get('chunk_size', 0))
                if configured_chunk > 0:
                    chunk_size = configured_chunk
                    logger.debug(f"Using configured chunk size: {chunk_size/(1024*1024):.0f}MB")
            except Exception:
                pass

        # If still no chunk_size, use intelligent dynamic sizing
        if chunk_size is None or chunk_size == 0:
            chunk_size = self.calculate_optimal_chunk_size(file_size)

        # Enforce S3 minimum part size
        if chunk_size < min_part_size:
            chunk_size = min_part_size

        # Calculate number of parts
        part_count = (file_size + chunk_size - 1) // chunk_size

        # If too many parts, increase chunk size to stay well under 10,000 limit
        if part_count > max_parts:
            logger.warning(f"Part count {part_count} exceeds S3 limit, adjusting chunk size")
            # Leave some headroom (use 9,500 as practical limit)
            practical_max = 9500
            chunk_size = (file_size + practical_max - 1) // practical_max
            # Round up to nearest 10MB for efficiency
            mb = 1024 * 1024
            chunk_size = ((chunk_size + (10 * mb) - 1) // (10 * mb)) * (10 * mb)
            part_count = (file_size + chunk_size - 1) // chunk_size
            logger.info(f"Adjusted to {chunk_size/mb:.0f}MB chunks to stay under part limit")

        # Log final calculation
        mb = 1024 * 1024
        logger.debug(f"Multipart calculation complete: {part_count} parts × {chunk_size/mb:.1f}MB chunks = {file_size/mb:.1f}MB total")

        # Decide whether to use multipart based on configured threshold
        threshold = self._get_multipart_threshold()

        return {
            'should_use_multipart': file_size > threshold,
            'part_count': int(part_count),
            'chunk_size': int(chunk_size),
            'last_part_size': int(file_size % chunk_size if file_size % chunk_size > 0 else chunk_size),
            'total_size': int(file_size),
            'part_numbers': list(range(1, int(part_count) + 1))
        }

    def validate_file_upload(
        self,
        file_name: str,
        file_size: int,
        content_type: str,
        allowed_types: Optional[List[str]] = None,
        max_file_size: Optional[int] = None,
        min_file_size: int = 1
    ) -> Dict[str, Any]:
        """
        Validate file upload parameters.

        Args:
            file_name: Name of the file
            file_size: Size of the file in bytes
            content_type: MIME type of the file
            allowed_types: List of allowed MIME types
            max_file_size: Maximum file size in bytes
            min_file_size: Minimum file size in bytes

        Returns:
            Dict with validation result
        """
        errors = []
        warnings = []

        # File size validation
        if file_size < min_file_size:
            errors.append(f"File size must be at least {min_file_size} bytes")

        if max_file_size and file_size > max_file_size:
            errors.append(f"File size {file_size} exceeds maximum allowed size of {max_file_size} bytes")

        # File name validation
        if not file_name or file_name.strip() == '':
            errors.append("File name cannot be empty")

        # Content type validation
        if allowed_types and content_type not in allowed_types:
            errors.append(f"Content type '{content_type}' not allowed. Allowed types: {', '.join(allowed_types)}")

        # Large file recommendation
        single_upload_limit = 5 * 1024 * 1024 * 1024  # 5GB (S3 single PUT limit)
        if file_size > single_upload_limit:
            warnings.append("File exceeds single-upload limit; multipart is required.")

        threshold = self._get_multipart_threshold()

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'should_use_multipart': file_size > threshold
        }

    # ----- Multipart Upload Methods -----

    def initialize_multipart_upload(
        self,
        file_name: str,
        file_type: str,
        path_prefix: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a multipart upload to S3.
        
        Args:
            file_name (str): Name of the file to upload
            file_type (str): MIME type of the file
            path_prefix (str, optional): Folder path to prepend to the file name
            
        Returns:
            Dict[str, Any]: Dictionary containing upload ID and S3 key or error information
        """
        try:
            # Generate a clean S3 key for the file
            s3_key = self._generate_file_key(file_name, path_prefix)
            
            target_bucket = bucket_name or self.ingest_bucket
            logger.info(f"Initializing multipart upload for {s3_key} in {target_bucket}")
            
            # Create a multipart upload
            response = self.s3_client.create_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                ContentType=file_type
            )
            
            upload_id = response['UploadId']
            logger.info(f"Multipart upload initialized: {upload_id}")
            
            return {
                'success': True,
                'upload_id': upload_id,
                's3_key': s3_key,
                'file_name': file_name,
                'file_type': file_type,
                'bucket_name': target_bucket
            }
        except Exception as e:
            logger.error(f"Error initializing multipart upload for {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }
    
    def get_upload_part_urls(
        self,
        s3_key: str,
        upload_id: str,
        part_count: int,
        expiration: int = 3600,
        bucket_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate presigned URLs for each part of a multipart upload.
        
        Args:
            s3_key (str): The S3 key for the file
            upload_id (str): The multipart upload ID
            part_count (int): Number of parts to generate URLs for
            expiration (int): Time in seconds for the URLs to be valid
            
        Returns:
            Dict[str, Any]: Dictionary containing presigned URLs for each part or error information
        """
        try:
            presigned_urls = []
            
            target_bucket = bucket_name or self.ingest_bucket
            for part_number in range(1, part_count + 1):
                # Generate a presigned URL for this part using the presigned client
                url = self.presigned_client.generate_presigned_url(
                    'upload_part',
                    Params={
                        'Bucket': target_bucket,
                        'Key': s3_key,
                        'UploadId': upload_id,
                        'PartNumber': part_number
                    },
                    ExpiresIn=expiration
                )
                
                presigned_urls.append({
                    'part_number': part_number,
                    'url': url
                })
            
            logger.info(f"Generated {part_count} part upload URLs for {s3_key}")
            
            return {
                'success': True,
                'presigned_urls': presigned_urls,
                's3_key': s3_key,
                'upload_id': upload_id,
                'part_count': part_count,
                'bucket_name': target_bucket
            }
        except Exception as e:
            logger.error(f"Error generating part upload URLs for {s3_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                's3_key': s3_key,
                'upload_id': upload_id
            }
    
    def complete_multipart_upload(
        self,
        s3_key: str,
        upload_id: str,
        parts: List[Dict[str, Any]],
        bucket_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete a multipart upload by assembling all parts.
        
        Args:
            s3_key (str): The S3 key for the file
            upload_id (str): The multipart upload ID
            parts (List[Dict[str, Any]]): List of dictionaries with part_number and etag for each part
            
        Returns:
            Dict[str, Any]: Dictionary containing status information or error information
        """
        try:
            # Format the parts list for the API call
            multipart_parts = [
                {
                    'PartNumber': part['part_number'],
                    'ETag': part['etag']
                }
                for part in parts
            ]
            
            # Sort parts by part number to ensure correct order
            multipart_parts.sort(key=lambda x: x['PartNumber'])
            
            target_bucket = bucket_name or self.ingest_bucket
            logger.info(f"Completing multipart upload for {s3_key} in {target_bucket} with {len(multipart_parts)} parts")
            
            # Complete the multipart upload
            response = self.s3_client.complete_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={
                    'Parts': multipart_parts
                }
            )
            
            logger.info(f"Multipart upload completed: {response}")
            
            # Check if file exists and get metadata
            head_response = self.s3_client.head_object(
                Bucket=target_bucket,
                Key=s3_key
            )
            
            file_size = head_response.get('ContentLength', 0)
            
            return {
                'success': True,
                's3_key': s3_key,
                'location': response.get('Location', ''),
                'bucket': target_bucket,
                'key': s3_key,
                'etag': response.get('ETag', '').strip('"'),
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size)
            }
        except Exception as e:
            logger.error(f"Error completing multipart upload for {s3_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                's3_key': s3_key,
                'upload_id': upload_id
            }
    
    def abort_multipart_upload(
        self,
        s3_key: str,
        upload_id: str,
        bucket_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Abort a multipart upload and clean up any uploaded parts.
        
        Args:
            s3_key (str): The S3 key for the file
            upload_id (str): The multipart upload ID
            
        Returns:
            Dict[str, Any]: Dictionary containing status information or error information
        """
        try:
            target_bucket = bucket_name or self.ingest_bucket
            logger.info(f"Aborting multipart upload for {s3_key} in {target_bucket}")
            
            # Abort the multipart upload
            self.s3_client.abort_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                UploadId=upload_id
            )
            
            logger.info(f"Multipart upload aborted: {upload_id}")
            
            return {
                'success': True,
                's3_key': s3_key,
                'upload_id': upload_id
            }
        except Exception as e:
            logger.error(f"Error aborting multipart upload for {s3_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                's3_key': s3_key,
                'upload_id': upload_id
            }
    
    def list_multipart_uploads(self) -> Dict[str, Any]:
        """
        List all in-progress multipart uploads.
        
        Returns:
            Dict[str, Any]: Dictionary containing list of uploads or error information
        """
        try:
            logger.info(f"Listing multipart uploads for bucket {self.ingest_bucket}")
            
            # List multipart uploads
            response = self.s3_client.list_multipart_uploads(
                Bucket=self.ingest_bucket
            )
            
            uploads = []
            
            # Extract upload information
            for upload in response.get('Uploads', []):
                uploads.append({
                    's3_key': upload.get('Key', ''),
                    'upload_id': upload.get('UploadId', ''),
                    'initiated': upload.get('Initiated', ''),
                    'initiator': upload.get('Initiator', {}).get('DisplayName', '')
                })
            
            logger.info(f"Found {len(uploads)} in-progress multipart uploads")
            
            return {
                'success': True,
                'uploads': uploads,
                'count': len(uploads)
            }
        except Exception as e:
            logger.error(f"Error listing multipart uploads: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 
