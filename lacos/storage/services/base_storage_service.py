import logging
import os
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class BaseStorageService:
    """
    Base service for interacting with S3/MinIO storage.
    
    This service handles both local development with MinIO and production with S3.
    It automatically detects the environment and configures the client accordingly.
    """
    
    # Class-level flag to track if buckets have been checked
    _buckets_checked = False
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BaseStorageService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the BaseStorageService with S3 client.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check (for child services)
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        logger.info("Initializing BaseStorageService...")
        
        # Initialize settings
        self.is_minio = self._is_minio_environment()
        self.endpoint_url = self._get_endpoint_url()
        self.access_key = self._get_access_key()
        self.secret_key = self._get_secret_key()
        self.region = self._get_region()
        self.max_pool_connections = self._get_max_pool_connections()
        
        # Determine if we're running inside a container
        # This helps us decide how to handle URLs for browser access
        self.in_container = self._is_running_in_container()
        
        # Initialize workspace buckets (flexible configuration)
        self.workspace_buckets = self._get_workspace_buckets()
        # OCFL buckets will be determined dynamically

        # Initialize legacy buckets for backward compatibility
        self.ingest_bucket = self._get_ingest_bucket_name()
        self.production_bucket = self._get_production_bucket_name()

        # Create S3 client
        logger.info("Creating S3 client", extra={"endpoint_url": self.endpoint_url})
        self.s3_client = self._create_s3_client()

        logger.info("BaseStorageService initialized", extra={"backend": "MinIO" if self.is_minio else "S3"})
        logger.info("Using endpoint", extra={"endpoint_url": self.endpoint_url or "default S3 endpoint"})
        logger.info("Using region", extra={"region": self.region})
        logger.info("S3 max pool connections", extra={"max_pool_connections": self.max_pool_connections})
        logger.info("Workspace buckets", extra={"workspace_buckets": self.workspace_buckets})
        logger.info("All buckets are OCFL-capable")
        logger.info("Legacy ingest bucket", extra={"ingest_bucket": self.ingest_bucket})
        logger.info("Legacy production bucket", extra={"production_bucket": self.production_bucket})
        
        # Only check buckets if not skipped and not already checked
        if not skip_bucket_check and not self._buckets_checked:
            logger.info("Ensuring workspace buckets exist...")

            # Ensure all workspace buckets exist
            for bucket_name in self.workspace_buckets:
                bucket_exists = self.ensure_bucket_exists(bucket_name)
                if bucket_exists:
                    # Ensure CORS is configured for all buckets (needed for direct uploads and video streaming)
                    logger.info("Ensuring CORS is configured", extra={"bucket_name": bucket_name})
                    cors_result = self.ensure_cors_enabled(bucket_name)
                    if cors_result["success"]:
                        if cors_result.get("updated", False):
                            logger.info("CORS configuration has been updated", extra={"bucket_name": bucket_name})
                        else:
                            logger.info("CORS configuration is already correct", extra={"bucket_name": bucket_name})
                    else:
                        logger.warning("Failed to configure CORS", extra={"bucket_name": bucket_name, "error": cors_result.get('error', 'Unknown error')})

            # Set the class-level flag
            self._buckets_checked = True
        
        # Mark as initialized
        self.initialized = True
    
    def set_client_and_buckets(self, service):
        """
        Ensure a child service uses the same S3 client and bucket names.
        
        Args:
            service: The child service to update
        """
        if hasattr(service, 's3_client'):
            service.s3_client = self.s3_client
            
        if hasattr(service, 'ingest_bucket'):
            service.ingest_bucket = self.ingest_bucket
            
        if hasattr(service, 'production_bucket'):
            service.production_bucket = self.production_bucket
            
        return service
    
    def _is_minio_environment(self) -> bool:
        """Determine if we're using MinIO based on settings or environment."""
        # First check for explicit setting
        use_minio = getattr(settings, 'USE_MINIO', None)
        if use_minio is not None:
            return use_minio
        
        # Then check for environment variable
        use_minio_env = os.environ.get('USE_MINIO', '').lower()
        if use_minio_env in ('true', 'yes', '1'):
            return True
        elif use_minio_env in ('false', 'no', '0'):
            return False
        
        # Finally, check if we're in a development environment
        return getattr(settings, 'DEBUG', False)
    
    def _get_endpoint_url(self) -> str:
        """Get the endpoint URL for S3/MinIO."""
        # First check for explicit setting
        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_url:
            return endpoint_url
        
        # Then check for environment variable
        endpoint_url_env = os.environ.get('AWS_S3_ENDPOINT_URL', '')
        if endpoint_url_env:
            return endpoint_url_env
        
        # Default MinIO endpoint if we're using MinIO
        if self._is_minio_environment():
            return 'http://minio:9000'
        
        # For production S3, return None to use the default AWS endpoint
        return None
    
    def _get_access_key(self) -> str:
        """Get the access key for S3/MinIO."""
        # First check for explicit setting
        access_key = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        if access_key:
            return access_key
        
        # Then check for environment variable
        access_key_env = os.environ.get('AWS_ACCESS_KEY_ID', '')
        if access_key_env:
            return access_key_env
        
        # Default MinIO access key if we're using MinIO
        if self._is_minio_environment():
            return 'minioadmin'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_ACCESS_KEY_ID found in settings or environment")
        return ''
    
    def _get_secret_key(self) -> str:
        """Get the secret key for S3/MinIO."""
        # First check for explicit setting
        secret_key = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        if secret_key:
            return secret_key
        
        # Then check for environment variable
        secret_key_env = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
        if secret_key_env:
            return secret_key_env
        
        # Default MinIO secret key if we're using MinIO
        if self._is_minio_environment():
            return 'minioadmin'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_SECRET_ACCESS_KEY found in settings or environment")
        return ''
    
    def _get_region(self) -> str:
        """Get the region for S3."""
        # First check for explicit setting
        region = getattr(settings, 'AWS_S3_REGION_NAME', None)
        if region:
            return region
        
        # Then check for environment variable
        region_env = os.environ.get('AWS_S3_REGION_NAME', '')
        if region_env:
            return region_env
        
        # Default region
        return 'us-east-1'

    def _get_max_pool_connections(self) -> int:
        """Get max HTTP connection pool size for botocore clients."""
        configured = getattr(settings, 'AWS_S3_MAX_POOL_CONNECTIONS', 50)
        try:
            parsed = int(configured)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid AWS_S3_MAX_POOL_CONNECTIONS value %r. Falling back to 50.",
                configured,
            )
            parsed = 50
        return max(1, parsed)
    
    def _get_ingest_bucket_name(self) -> str:
        """Get the ingest bucket name for S3/MinIO."""
        # First check for explicit setting
        bucket_name = getattr(settings, 'AWS_INGEST_BUCKET_NAME', None)
        if bucket_name:
            return bucket_name
        
        # Then check for environment variable
        bucket_name_env = os.environ.get('AWS_INGEST_BUCKET_NAME', '')
        if bucket_name_env:
            return bucket_name_env
        
        # Fall back to the storage bucket name if ingest-specific not defined
        storage_bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        if storage_bucket:
            return storage_bucket
            
        storage_bucket_env = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
        if storage_bucket_env:
            return storage_bucket_env

        legacy_bucket = getattr(settings, 'S3_INGEST_BUCKET', None)
        if legacy_bucket:
            logger.warning(
                "S3_INGEST_BUCKET is deprecated; use AWS_STORAGE_BUCKET_NAME instead."
            )
            return legacy_bucket

        legacy_bucket_env = os.environ.get('S3_INGEST_BUCKET', '')
        if legacy_bucket_env:
            logger.warning(
                "S3_INGEST_BUCKET is deprecated; use AWS_STORAGE_BUCKET_NAME instead."
            )
            return legacy_bucket_env
        
        # Default bucket name
        if self._is_minio_environment():
            return 'lacos-ingest'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_INGEST_BUCKET_NAME found in settings or environment")
        return 'lacos-ingest'
    
    def _get_production_bucket_name(self) -> str:
        """Get the production bucket name for S3/MinIO."""
        # First check for explicit setting
        bucket_name = getattr(settings, 'AWS_PRODUCTION_BUCKET_NAME', None)
        if bucket_name:
            return bucket_name
        
        # Then check for environment variable
        bucket_name_env = os.environ.get('AWS_PRODUCTION_BUCKET_NAME', '')
        if bucket_name_env:
            return bucket_name_env

        legacy_bucket = getattr(settings, 'S3_PRODUCTION_BUCKET', None)
        if legacy_bucket:
            logger.warning(
                "S3_PRODUCTION_BUCKET is deprecated; use AWS_PRODUCTION_BUCKET_NAME instead."
            )
            return legacy_bucket

        legacy_bucket_env = os.environ.get('S3_PRODUCTION_BUCKET', '')
        if legacy_bucket_env:
            logger.warning(
                "S3_PRODUCTION_BUCKET is deprecated; use AWS_PRODUCTION_BUCKET_NAME instead."
            )
            return legacy_bucket_env
        
        # Default bucket name
        if self._is_minio_environment():
            return 'lacos-production'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_PRODUCTION_BUCKET_NAME found in settings or environment")
        return 'lacos-production'

    def _get_workspace_buckets(self) -> list:
        """Get the list of workspace buckets from settings."""
        workspace_buckets = getattr(settings, 'S3_WORKSPACE_BUCKETS', ['ingest', 'production'])
        logger.info("Loaded workspace buckets from settings", extra={"workspace_buckets": workspace_buckets})
        return workspace_buckets

    @property
    def ocfl_buckets(self) -> list:
        """Get all accessible buckets as OCFL-capable buckets."""
        return self.get_all_accessible_buckets()

    def is_ocfl_bucket(self, bucket_name: str) -> bool:
        """Check if a bucket allows OCFL operations. All buckets are OCFL-capable."""
        return True

    def get_all_accessible_buckets(self) -> list:
        """Get all buckets that exist in MinIO."""
        cache_key = "storage:bucket-names"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Returning cached bucket list: %s", cached)
            return cached

        try:
            response = self.s3_client.list_buckets()
            bucket_names = sorted(bucket['Name'] for bucket in response['Buckets'])
            logger.info("📦 BUCKETS: Found %s buckets in MinIO", len(bucket_names))
            cache.set(cache_key, bucket_names, timeout=300)
            return bucket_names
        except Exception as e:
            logger.exception("❌ Error listing buckets from MinIO: %s", e)
            return self.workspace_buckets.copy()

    def _create_s3_client(self):
        """
        Create an S3 client configured for the current environment.
        
        Returns:
            boto3.client: Configured S3 client
        """
        # Basic client configuration
        client_kwargs = {
            'service_name': 's3',
            'aws_access_key_id': self.access_key,
            'aws_secret_access_key': self.secret_key,
        }
        config_kwargs = {
            'max_pool_connections': self.max_pool_connections,
        }
        
        # Add region if specified
        if self.region:
            client_kwargs['region_name'] = self.region
        
        # Add endpoint URL for MinIO or custom S3 endpoints
        if self.endpoint_url:
            # For server-side operations, use the original endpoint URL
            server_endpoint = self.endpoint_url
            client_kwargs['endpoint_url'] = server_endpoint
            
            # S3-compatible endpoints (MinIO, Dell ECS) need path-style addressing
            config_kwargs['signature_version'] = os.environ.get('AWS_S3_SIGNATURE_VERSION', 's3v4')
            config_kwargs['s3'] = {'addressing_style': 'path'}
            # Dell ECS doesn't support newer checksum headers (x-amz-checksum-crc32)
            config_kwargs['request_checksum_calculation'] = 'when_required'
            config_kwargs['response_checksum_validation'] = 'when_required'

            # For MinIO in local development, we need special handling for presigned URLs
            if self.is_minio:
                
                # For presigned URLs that will be used by the browser,
                # we need to use a browser-accessible URL
                browser_endpoint = os.environ.get('AWS_S3_BROWSER_ENDPOINT_URL', None)
                
                if browser_endpoint:
                    logger.info("Using browser endpoint URL from environment", extra={"browser_endpoint": browser_endpoint})
                elif 'minio:9000' in self.endpoint_url:
                    # Default fallback for local development
                    browser_endpoint = self.endpoint_url.replace('minio:9000', 'localhost:9000')
                    logger.info("MinIO detected, will use browser endpoint for presigned URLs", extra={"endpoint_url": self.endpoint_url, "browser_endpoint": browser_endpoint})
                else:
                    # If no specific browser endpoint is provided, use the same as server
                    browser_endpoint = self.endpoint_url
                    logger.info("Using server endpoint for presigned URLs", extra={"browser_endpoint": browser_endpoint})
                
                # Create a separate client for generating presigned URLs
                self.presigned_client = boto3.client(
                    's3',
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region if self.region else None,
                    endpoint_url=browser_endpoint,
                    config=boto3.session.Config(**config_kwargs)
                )
                logger.info("Created separate client for presigned URLs", extra={"browser_endpoint": browser_endpoint})

        client_kwargs['config'] = boto3.session.Config(**config_kwargs)
        
        # Create the primary client
        client = boto3.client(**client_kwargs)

        # Ensure a presigned client always exists; fall back to the primary client
        if not hasattr(self, "presigned_client"):
            self.presigned_client = client

        return client
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def ensure_bucket_exists(self, bucket_name: str) -> bool:
        """
        Ensure that the specified bucket exists, creating it if necessary.
        
        Args:
            bucket_name (str): The name of the bucket to check/create.
            
        Returns:
            bool: True if the bucket exists or was created successfully, False otherwise.
        """
        logger.info("Checking if bucket exists", extra={"bucket_name": bucket_name})
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info("Bucket already exists", extra={"bucket_name": bucket_name})
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.info("Bucket check result", extra={"error_code": error_code, "error_message": error_message})
            
            # If bucket doesn't exist, create it
            if error_code == '404' or error_code == 'NoSuchBucket':
                try:
                    logger.info("Creating bucket", extra={"bucket_name": bucket_name, "region": self.region})
                    if self.region == 'us-east-1':
                        # Special case for us-east-1
                        logger.info("Using special case for us-east-1 region (no LocationConstraint)")
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        logger.info("Using LocationConstraint", extra={"region": self.region})
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info("Bucket created successfully", extra={"bucket_name": bucket_name})
                    return True
                except Exception as create_error:
                    logger.error("Error creating bucket", extra={"bucket_name": bucket_name, "error": str(create_error)})
                    # Log more details about the error
                    if hasattr(create_error, 'response'):
                        error_details = create_error.response.get('Error', {})
                        logger.error("Error details", extra={"code": error_details.get('Code'), "error_message": error_details.get('Message')})
                    return False
            else:
                logger.error("Error checking bucket", extra={"bucket_name": bucket_name, "error_code": error_code, "error_message": error_message})
                return False
    
    def get_file_content(self, bucket_name: str, file_path: str) -> Dict[str, Any]:
        """
        Get the content of a file from the specified bucket.
        
        Args:
            bucket_name (str): The name of the bucket containing the file
            file_path (str): The path to the file in the bucket
            
        Returns:
            Dict[str, Any]: A dictionary containing the file content and metadata
        """
        try:
            response = self.s3_client.get_object(
                Bucket=bucket_name, Key=file_path
            )
            
            # Get the file content
            content = response["Body"].read()
            
            # Get the file metadata
            metadata = {
                "content_type": response.get("ContentType", "application/octet-stream"),
                "content_length": response.get("ContentLength", 0),
                "last_modified": response.get("LastModified", None),
            }
            
            return {
                "content": content,
                "metadata": metadata,
                "bucket_type": "ingest" if bucket_name == self.ingest_bucket else "production",
                "path": file_path,
            }
        except ClientError as e:
            logger.error("Error getting file content", extra={"file_path": file_path, "error": str(e)})
            return {"error": str(e)}
            
    def delete_object(self, bucket_name: str, object_path: str, is_directory: bool = False) -> Dict[str, Any]:
        """
        Delete an object or directory from the specified bucket.
        
        Args:
            bucket_name (str): The name of the bucket containing the object
            object_path (str): The path to the object in the bucket
            is_directory (bool, optional): Whether the object is a directory. Defaults to False.
            
        Returns:
            Dict[str, Any]: A dictionary containing the result of the operation
        """
        try:
            if is_directory:
                # For directories, we need to delete all objects with the given prefix
                paginator = self.s3_client.get_paginator("list_objects_v2")
                
                objects_to_delete = []
                for page in paginator.paginate(Bucket=bucket_name, Prefix=object_path):
                    for obj in page.get("Contents", []):
                        objects_to_delete.append({"Key": obj["Key"]})
                
                if objects_to_delete:
                    # Some S3-compatible services (like MinIO) require Content-MD5 for DeleteObjects
                    # We'll delete each object individually to avoid this issue
                    logger.info("Deleting objects from bucket", extra={"count": len(objects_to_delete), "bucket_name": bucket_name, "object_path": object_path})
                    deleted_count = 0
                    for obj in objects_to_delete:
                        try:
                            self.s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                            deleted_count += 1
                        except Exception as obj_error:
                            logger.error("Error deleting object", extra={"key": obj['Key'], "error": str(obj_error)})
                    
                    return {
                        "success": deleted_count > 0,
                        "message": f"Successfully deleted directory {object_path} with {deleted_count} objects",
                        "deleted_objects": deleted_count
                    }
                else:
                    return {
                        "success": True,
                        "message": f"Directory {object_path} was empty, nothing to delete",
                        "deleted_objects": 0
                    }
            else:
                # For single objects, just delete the object
                self.s3_client.delete_object(Bucket=bucket_name, Key=object_path)
                
                return {
                    "success": True,
                    "message": f"Successfully deleted object {object_path}",
                    "deleted_objects": 1
                }
        except ClientError as e:
            logger.error("Error deleting object", extra={"object_path": object_path, "error": str(e)})
            return {"success": False, "error": str(e)}
    
    def ensure_cors_enabled(self, bucket_name: str = None) -> Dict[str, Any]:
        """
        Ensure CORS is properly configured for the specified bucket.
        
        This is required for browser-based uploads to work properly.
        
        Args:
            bucket_name (str, optional): Name of the bucket to configure. 
                                         Defaults to ingest bucket.
        
        Returns:
            Dict[str, Any]: Result of the operation
        """
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        
        logger.info("Checking CORS configuration for bucket", extra={"bucket_name": bucket_name})

        # MinIO does not implement PutBucketCors / GetBucketCors.
        # Skip entirely to avoid noisy ERROR logs on every startup.
        if self.is_minio:
            logger.debug("Skipping CORS configuration for MinIO (not supported)")
            return {"success": True, "message": "CORS configuration skipped for MinIO", "updated": False}

        try:
            # Define the required CORS rule for uploads and video streaming with range requests
            required_rule = {
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['GET', 'HEAD', 'PUT', 'POST', 'DELETE'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': ['Content-Range', 'Accept-Ranges', 'Content-Length', 'ETag']
            }
            
            # Check if CORS is already configured
            try:
                cors_config = self.s3_client.get_bucket_cors(Bucket=bucket_name)
                current_rules = cors_config.get('CORSRules', [])
                logger.info("Found existing CORS configuration", extra={"rule_count": len(current_rules)})
                
                # Check if our required rule already exists
                rule_exists = False
                for rule in current_rules:
                    # Check if all required keys are in the existing rule
                    if (set(rule.get('AllowedHeaders', [])) >= set(required_rule['AllowedHeaders']) and
                        set(rule.get('AllowedMethods', [])) >= set(required_rule['AllowedMethods']) and
                        set(rule.get('AllowedOrigins', [])) >= set(required_rule['AllowedOrigins']) and
                        set(rule.get('ExposeHeaders', [])) >= set(required_rule['ExposeHeaders'])):
                        rule_exists = True
                        logger.info("✅ Required CORS rule already exists")
                        break
                
                # If the rule doesn't exist, add it
                if not rule_exists:
                    logger.info("🔄 Required CORS rule not found, updating configuration...")
                    
                    # Use existing rules if any, otherwise create a new configuration
                    new_rules = current_rules.copy() if current_rules else []
                    new_rules.append(required_rule)
                    
                    # Apply the updated CORS configuration
                    self.s3_client.put_bucket_cors(
                        Bucket=bucket_name,
                        CORSConfiguration={'CORSRules': new_rules}
                    )
                    logger.info("✅ CORS configuration updated successfully")
                    return {"success": True, "message": "CORS configuration updated", "updated": True}
                
                return {"success": True, "message": "CORS already properly configured", "updated": False}
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                error_message = e.response.get('Error', {}).get('Message', str(e))
                
                # If no CORS configuration exists, create one
                if error_code == 'NoSuchCORSConfiguration':
                    logger.info("No existing CORS configuration found, creating new configuration...")
                    
                    # Create a new CORS configuration with our required rule
                    self.s3_client.put_bucket_cors(
                        Bucket=bucket_name,
                        CORSConfiguration={'CORSRules': [required_rule]}
                    )
                    logger.info("✅ CORS configuration created successfully")
                    return {"success": True, "message": "CORS configuration created", "updated": True}
                else:
                    # Some other error occurred
                    logger.error("Error getting CORS configuration", extra={"error_code": error_code, "error_message": error_message})
                    return {"success": False, "error": f"{error_code}: {error_message}"}
        
        except Exception as e:
            logger.error("Error ensuring CORS configuration", extra={"error": str(e)})
            return {"success": False, "error": str(e)}

    def _is_running_in_container(self):
        """
        Determine if we're running inside a Docker container.
        
        Returns:
            bool: True if running in a container, False otherwise
        """
        # Check for the RUNNING_IN_CONTAINER environment variable
        if os.environ.get('RUNNING_IN_CONTAINER'):
            return True
        
        # Check for .dockerenv file
        if os.path.exists('/.dockerenv'):
            return True
        
        # Check cgroup
        try:
            with open('/proc/1/cgroup', 'r') as f:
                return 'docker' in f.read() or 'kubepods' in f.read()
        except:
            pass
        
        return False 
