import logging
import os
from typing import Dict, Any, List, Optional
from pathlib import PurePosixPath

import boto3

from .base_storage_service import BaseStorageService
from .upload_content_inspection import inspect_uploaded_content, normalize_content_type

logger = logging.getLogger(__name__)


DEFAULT_ALLOWED_CONTENT_TYPES = {
    "application/gzip",
    "application/json",
    "application/octet-stream",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-7z-compressed",
    "application/x-bzip2",
    "application/x-tar",
    "application/xml",
    "application/zip",
    "text/csv",
    "text/markdown",
    "text/plain",
    "text/tab-separated-values",
    "text/xml",
}

DEFAULT_ALLOWED_CONTENT_TYPE_PREFIXES = (
    "audio/",
    "image/",
    "text/",
    "video/",
)

DEFAULT_BLOCKED_CONTENT_TYPES = {
    "application/javascript",
    "application/x-bat",
    "application/x-csh",
    "application/x-httpd-php",
    "application/x-msdownload",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/html",
    "text/javascript",
}

DEFAULT_BLOCKED_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".cjs",
    ".exe",
    ".htm",
    ".html",
    ".js",
    ".mjs",
    ".php",
    ".ps1",
    ".sh",
    ".svg",
}


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

    def _get_upload_security_settings(self) -> Dict[str, Any]:
        try:
            from django.conf import settings
        except Exception:
            return {
                "allowed_types": set(DEFAULT_ALLOWED_CONTENT_TYPES),
                "allowed_type_prefixes": tuple(DEFAULT_ALLOWED_CONTENT_TYPE_PREFIXES),
                "blocked_types": set(DEFAULT_BLOCKED_CONTENT_TYPES),
                "blocked_extensions": set(DEFAULT_BLOCKED_EXTENSIONS),
                "max_file_size": 50 * 1024 * 1024 * 1024,
                "min_file_size": 1,
            }

        return {
            "allowed_types": set(
                getattr(settings, "UPLOAD_ALLOWED_CONTENT_TYPES", DEFAULT_ALLOWED_CONTENT_TYPES),
            ),
            "allowed_type_prefixes": tuple(
                getattr(
                    settings,
                    "UPLOAD_ALLOWED_CONTENT_TYPE_PREFIXES",
                    DEFAULT_ALLOWED_CONTENT_TYPE_PREFIXES,
                ),
            ),
            "blocked_types": set(
                getattr(settings, "UPLOAD_BLOCKED_CONTENT_TYPES", DEFAULT_BLOCKED_CONTENT_TYPES),
            ),
            "blocked_extensions": set(
                getattr(settings, "UPLOAD_BLOCKED_EXTENSIONS", DEFAULT_BLOCKED_EXTENSIONS),
            ),
            "max_file_size": int(
                getattr(settings, "UPLOAD_MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024 * 1024),
            ),
            "min_file_size": int(getattr(settings, "UPLOAD_MIN_FILE_SIZE_BYTES", 1)),
        }

    def _normalize_content_type(self, content_type: Optional[str]) -> str:
        return normalize_content_type(content_type)

    def _read_upload_sample(self, bucket_name: str, s3_key: str, *, sample_bytes: int = 8192) -> bytes:
        response = self.s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        body = response.get("Body")
        if body is None:
            return b""

        try:
            return body.read(sample_bytes)
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

    def _normalize_path_prefix(self, path_prefix: Optional[str]) -> str:
        if not path_prefix:
            return ""

        cleaned = path_prefix.replace("\\", "/").strip("/")
        if "\x00" in cleaned:
            raise ValueError("Path prefix contains invalid characters")

        parts: list[str] = []
        for part in PurePosixPath(cleaned).parts:
            if part in ("", "."):
                continue
            if part == "..":
                raise ValueError("Path prefix cannot contain parent directory traversal")
            parts.append(part)
        return "/".join(parts)

    def _validate_file_name(self, file_name: Optional[str]) -> str:
        if not file_name or not file_name.strip():
            raise ValueError("File name cannot be empty")

        normalized = file_name.strip()
        if "\x00" in normalized:
            raise ValueError("File name contains invalid characters")
        if "/" in normalized or "\\" in normalized:
            raise ValueError("File name must not contain path separators")
        if normalized in {".", ".."}:
            raise ValueError("File name is invalid")
        return normalized

    def _generate_file_key(self, file_name: str, path_prefix: Optional[str] = None) -> str:
        """
        Generate a clean S3 key (path) for a file.
        
        Args:
            file_name (str): The name of the file
            path_prefix (str, optional): Path prefix to prepend to the file name
            
        Returns:
            str: The generated S3 key
        """
        validated_file_name = self._validate_file_name(file_name)
        clean_file_name = validated_file_name.replace(' ', '_')
        
        # Build the full S3 key (path)
        if path_prefix:
            clean_prefix = self._normalize_path_prefix(path_prefix)
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
            security_settings = self._get_upload_security_settings()
            validation = self.validate_file_upload(
                file_name=file_name,
                file_size=file_size,
                content_type=file_type,
                allowed_types=list(security_settings["allowed_types"]),
                max_file_size=security_settings["max_file_size"],
                min_file_size=security_settings["min_file_size"],
            )
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "; ".join(validation["errors"]),
                }

            file_name = validation["file_name"]
            file_type = validation["content_type"]
            path_prefix = self._normalize_path_prefix(path_prefix)
            # Generate a unique key for the file
            file_key = self._generate_file_key(file_name, path_prefix)

            logger.info("Generating presigned upload URL", extra={"file_key": file_key})

            # Check if multipart is needed based on file size
            threshold = self._get_multipart_threshold()
            size_for_parts = file_size if file_size > 0 else threshold + 1
            parts_info = self.calculate_multipart_parts(size_for_parts)

            if parts_info['should_use_multipart'] or file_size <= 0:
                    logger.info("File size exceeds threshold, using multipart upload", extra={"file_size": file_size})

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

            # Single-part upload for smaller files requires an explicit browser endpoint.
            client = self.get_presigned_client()

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
                    {'Content-Type': file_type},
                    ["content-length-range", security_settings["min_file_size"], security_settings["max_file_size"]],
                ],
                ExpiresIn=expiration
            )
            logger.info(
                "Generated presigned upload policy",
                extra={"file_key": file_key, "bucket": target_bucket, "upload_type": "single"},
            )
            
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
            logger.error("Error generating presigned POST", extra={"file_name": file_name, "error": str(e)})
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
        try:
            normalized_path_prefix = self._normalize_path_prefix(path_prefix)
        except ValueError as exc:
            return {
                'success': False,
                'presigned_posts': [],
                'failures': [{'file_meta': {}, 'error': str(exc)}],
                'total_urls': 0,
                'total_failures': 1,
            }
        
        for file_meta in files_metadata:
            file_name = file_meta.get('file_name')
            file_type = file_meta.get('file_type')
            file_path = file_meta.get('path')  # Get the optional file-specific path
            
            if not file_name or not file_type:
                logger.warning("Skipping invalid file metadata", extra={"file_meta": file_meta})
                failures.append({
                    'file_meta': file_meta,
                    'error': 'Missing file_name or file_type'
                })
                continue
            
            # Create effective path prefix by combining the overall prefix with file-specific path
            # Note: webkitRelativePath includes the filename, so we need to strip it
            effective_path_prefix = normalized_path_prefix
            if file_path:
                # Strip the filename from the path if it ends with the filename
                if file_path.endswith(file_name):
                    file_path = file_path[:-len(file_name)].rstrip('/')
                if file_path:  # Only use if there's still a path after stripping
                    try:
                        file_path = self._normalize_path_prefix(file_path)
                    except ValueError as exc:
                        failures.append({
                            'file_meta': file_meta,
                            'error': str(exc),
                        })
                        continue
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
                        logger.error("Missing multipart fields in result", extra={"file_name": file_name})
                        failures.append({
                            'file_meta': file_meta,
                            'error': "Missing multipart upload fields in server response"
                        })
                        continue
                else:
                    # For single uploads, validate presigned_post structure
                    if 'presigned_post' not in result:
                        logger.error("Missing presigned_post in result", extra={"file_name": file_name})
                        failures.append({
                            'file_meta': file_meta,
                            'error': "Missing presigned_post in server response"
                        })
                        continue

                    # Validate that presigned_post has url and fields
                    presigned_post = result['presigned_post']
                    if not isinstance(presigned_post, dict) or 'url' not in presigned_post or 'fields' not in presigned_post:
                        logger.error("Invalid presigned_post structure", extra={"file_name": file_name, "presigned_post": presigned_post})
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
            security_settings = self._get_upload_security_settings()
            validation = self.validate_file_upload(
                file_name=file_name,
                file_size=0,
                content_type=file_type,
                allowed_types=list(security_settings["allowed_types"]),
                max_file_size=security_settings["max_file_size"],
                min_file_size=security_settings["min_file_size"],
            )
            if not validation["valid"]:
                return {
                    'success': False,
                    'error': "; ".join(validation["errors"]),
                    'file_name': file_name,
                }

            file_name = validation["file_name"]
            file_type = validation["content_type"]
            clean_file_name = file_name.replace(' ', '_')
            
            # Build the full S3 key (path)
            s3_key = clean_file_name
            if path_prefix:
                path_prefix = self._normalize_path_prefix(path_prefix)
                if path_prefix:
                    s3_key = f"{path_prefix}/{clean_file_name}"
            
            logger.info("Generating accelerated upload URL", extra={"s3_key": s3_key})
            
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
                    {'Content-Type': file_type},
                    ["content-length-range", security_settings["min_file_size"], security_settings["max_file_size"]],
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
            logger.error("Error generating accelerated upload URL", extra={"file_name": file_name, "error": str(e)})
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
            security_settings = self._get_upload_security_settings()
            # Check if the file exists in S3
            response = self.s3_client.head_object(
                Bucket=target_bucket,
                Key=s3_key
            )
            
            file_size = response.get('ContentLength', 0)
            content_type = self._normalize_content_type(
                response.get('ContentType', 'application/octet-stream'),
            )
            last_modified = response.get('LastModified', None)
            etag = response.get('ETag', '').strip('"')
            sample_bytes = self._read_upload_sample(target_bucket, s3_key)
            inspection = inspect_uploaded_content(
                file_name=os.path.basename(s3_key),
                declared_content_type=content_type,
                sample_bytes=sample_bytes,
                blocked_content_types=security_settings["blocked_types"],
            )
            effective_content_type = inspection.detected_content_type or content_type
            validation = self.validate_file_upload(
                file_name=os.path.basename(s3_key),
                file_size=file_size,
                content_type=effective_content_type,
                allowed_types=list(security_settings["allowed_types"]),
                max_file_size=security_settings["max_file_size"],
                min_file_size=security_settings["min_file_size"],
            )
            errors = [*inspection.errors, *validation["errors"]]
            if errors:
                return {
                    'success': False,
                    'error': "; ".join(errors),
                    's3_key': s3_key,
                    'exists': True,
                    'file_size': file_size,
                    'content_type': effective_content_type,
                    'detected_content_type': inspection.detected_content_type,
                    'bucket_name': target_bucket,
                }
            
            return {
                'success': True,
                's3_key': s3_key,
                'exists': True,
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size),
                'content_type': effective_content_type,
                'detected_content_type': inspection.detected_content_type,
                'last_modified': last_modified.isoformat() if last_modified else None,
                'etag': etag,
                'bucket_name': target_bucket,
            }
            
        except Exception as e:
            logger.error("Error verifying uploaded file", extra={"s3_key": s3_key, "error": str(e)})
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
            logger.debug("Calculating multipart chunks for file", extra={"size_gb": round(size_gb, 2)})
        else:
            logger.debug("Calculating multipart chunks for file", extra={"size_mb": round(size_mb, 1)})

        # Optimized chunk sizes to minimize parts while maintaining performance
        if file_size <= 500 * MB:
            # 100-500MB: Use 25MB chunks (results in 4-20 parts)
            chunk_size = 25 * MB
            logger.debug("Using 25MB chunks for small file", extra={"size_mb": round(size_mb, 1)})
        elif file_size <= 1 * GB:
            # 500MB-1GB: Use 50MB chunks (results in 10-20 parts)
            chunk_size = 50 * MB
            logger.debug("Using 50MB chunks for medium file", extra={"size_mb": round(size_mb, 1)})
        elif file_size <= 5 * GB:
            # 1GB-5GB: Use 100MB chunks (results in 10-50 parts)
            chunk_size = 100 * MB
            logger.debug("Using 100MB chunks for large file", extra={"size_gb": round(size_gb, 2)})
        elif file_size <= 50 * GB:
            # 5GB-50GB: Use 250MB chunks (results in 20-200 parts)
            chunk_size = 250 * MB
            logger.debug("Using 250MB chunks for very large file", extra={"size_gb": round(size_gb, 2)})
        else:
            # >50GB: Calculate to keep parts around 500-1000
            target_parts = 750  # Aim for middle of range
            chunk_size = (file_size + target_parts - 1) // target_parts
            # Round up to nearest 50MB for consistency
            chunk_size = ((chunk_size + (50 * MB) - 1) // (50 * MB)) * (50 * MB)
            logger.debug("Using dynamic chunks for huge file", extra={"chunk_size_mb": round(chunk_size / MB), "size_gb": round(size_gb, 2)})

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
                    logger.debug("Using configured chunk size", extra={"chunk_size_mb": round(chunk_size / (1024 * 1024))})
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
            logger.warning("Part count exceeds S3 limit, adjusting chunk size", extra={"part_count": part_count})
            # Leave some headroom (use 9,500 as practical limit)
            practical_max = 9500
            chunk_size = (file_size + practical_max - 1) // practical_max
            # Round up to nearest 10MB for efficiency
            mb = 1024 * 1024
            chunk_size = ((chunk_size + (10 * mb) - 1) // (10 * mb)) * (10 * mb)
            part_count = (file_size + chunk_size - 1) // chunk_size
            logger.info("Adjusted chunk size to stay under part limit", extra={"chunk_size_mb": round(chunk_size / mb)})

        # Log final calculation
        mb = 1024 * 1024
        logger.debug("Multipart calculation complete", extra={"part_count": part_count, "chunk_size_mb": round(chunk_size / mb, 1), "total_size_mb": round(file_size / mb, 1)})

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
        security_settings = self._get_upload_security_settings()
        errors = []
        warnings = []
        normalized_file_name = file_name.strip() if isinstance(file_name, str) else ""
        normalized_content_type = self._normalize_content_type(content_type)

        if not normalized_content_type:
            errors.append("Content type is required")

        try:
            normalized_file_name = self._validate_file_name(normalized_file_name)
        except ValueError as exc:
            errors.append(str(exc))

        file_extension = os.path.splitext(normalized_file_name)[1].lower() if normalized_file_name else ""

        if file_extension in security_settings["blocked_extensions"]:
            errors.append(f"Files with extension '{file_extension}' are not allowed")

        if normalized_content_type in security_settings["blocked_types"]:
            errors.append(f"Content type '{normalized_content_type}' is not allowed")

        effective_allowed_types = {
            self._normalize_content_type(item) for item in (allowed_types or security_settings["allowed_types"])
        }
        allowed_prefixes = tuple(security_settings["allowed_type_prefixes"])
        if normalized_content_type and not (
            normalized_content_type in effective_allowed_types
            or any(normalized_content_type.startswith(prefix) for prefix in allowed_prefixes)
        ):
            errors.append(
                f"Content type '{normalized_content_type}' is not allowed for direct upload",
            )

        # File size validation
        if file_size and file_size > 0:
            if file_size < min_file_size:
                errors.append(f"File size must be at least {min_file_size} bytes")

            if max_file_size and file_size > max_file_size:
                errors.append(f"File size {file_size} exceeds maximum allowed size of {max_file_size} bytes")
        else:
            warnings.append("File size not provided; upload will be validated using multipart safeguards.")

        # Large file recommendation
        single_upload_limit = 5 * 1024 * 1024 * 1024  # 5GB (S3 single PUT limit)
        if file_size > single_upload_limit:
            warnings.append("File exceeds single-upload limit; multipart is required.")

        threshold = self._get_multipart_threshold()

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'should_use_multipart': file_size <= 0 or file_size > threshold,
            'file_name': normalized_file_name,
            'content_type': normalized_content_type,
        }

    # ----- Multipart Upload Methods -----

    def initialize_multipart_upload(
        self,
        file_name: str,
        file_type: str,
        path_prefix: Optional[str] = None,
        bucket_name: Optional[str] = None,
        file_size: Optional[int] = None,
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
            security_settings = self._get_upload_security_settings()
            validation = self.validate_file_upload(
                file_name=file_name,
                file_size=file_size or 0,
                content_type=file_type,
                allowed_types=list(security_settings["allowed_types"]),
                max_file_size=security_settings["max_file_size"],
                min_file_size=security_settings["min_file_size"],
            )
            if not validation["valid"]:
                return {
                    'success': False,
                    'error': "; ".join(validation["errors"]),
                    'file_name': file_name,
                }

            file_name = validation["file_name"]
            file_type = validation["content_type"]
            path_prefix = self._normalize_path_prefix(path_prefix)
            # Generate a clean S3 key for the file
            s3_key = self._generate_file_key(file_name, path_prefix)
            
            target_bucket = bucket_name or self.ingest_bucket
            logger.info("Initializing multipart upload", extra={"s3_key": s3_key, "bucket": target_bucket})
            
            # Create a multipart upload
            response = self.s3_client.create_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                ContentType=file_type
            )
            
            upload_id = response['UploadId']
            logger.info("Multipart upload initialized", extra={"upload_id": upload_id})
            
            return {
                'success': True,
                'upload_id': upload_id,
                's3_key': s3_key,
                'file_name': file_name,
                'file_type': file_type,
                'bucket_name': target_bucket
            }
        except Exception as e:
            logger.error("Error initializing multipart upload", extra={"file_name": file_name, "error": str(e)})
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
                url = self.get_presigned_client().generate_presigned_url(
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
            
            logger.info("Generated part upload URLs", extra={"part_count": part_count, "s3_key": s3_key})
            
            return {
                'success': True,
                'presigned_urls': presigned_urls,
                's3_key': s3_key,
                'upload_id': upload_id,
                'part_count': part_count,
                'bucket_name': target_bucket
            }
        except Exception as e:
            logger.error("Error generating part upload URLs", extra={"s3_key": s3_key, "error": str(e)})
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
            logger.info("Completing multipart upload", extra={"s3_key": s3_key, "bucket": target_bucket, "parts_count": len(multipart_parts)})
            
            # Complete the multipart upload
            response = self.s3_client.complete_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={
                    'Parts': multipart_parts
                }
            )
            
            logger.info("Multipart upload completed", extra={"response": response})
            
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
            logger.error("Error completing multipart upload", extra={"s3_key": s3_key, "error": str(e)})
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
            logger.info("Aborting multipart upload", extra={"s3_key": s3_key, "bucket": target_bucket})
            
            # Abort the multipart upload
            self.s3_client.abort_multipart_upload(
                Bucket=target_bucket,
                Key=s3_key,
                UploadId=upload_id
            )
            
            logger.info("Multipart upload aborted", extra={"upload_id": upload_id})
            
            return {
                'success': True,
                's3_key': s3_key,
                'upload_id': upload_id
            }
        except Exception as e:
            logger.error("Error aborting multipart upload", extra={"s3_key": s3_key, "error": str(e)})
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
            logger.info("Listing multipart uploads for bucket", extra={"bucket": self.ingest_bucket})
            
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
            
            logger.info("Found in-progress multipart uploads", extra={"count": len(uploads)})
            
            return {
                'success': True,
                'uploads': uploads,
                'count': len(uploads)
            }
        except Exception as e:
            logger.error("Error listing multipart uploads", extra={"error": str(e)})
            return {
                'success': False,
                'error': str(e)
            } 
