import logging
import os
from typing import Any, Dict, Optional, Generator
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
        logger.info(f"Creating S3 client with endpoint URL: {self.endpoint_url}")
        self.s3_client = self._create_s3_client()

        logger.info(f"BaseStorageService initialized with {'MinIO' if self.is_minio else 'S3'}")
        logger.info(f"Using endpoint: {self.endpoint_url or 'default S3 endpoint'}")
        logger.info(f"Using region: {self.region}")
        logger.info(f"Workspace buckets: {self.workspace_buckets}")

        # Only log legacy buckets if they're explicitly configured (not derived)
        explicit_ingest = getattr(settings, 'S3_INGEST_BUCKET', None) or getattr(settings, 'AWS_INGEST_BUCKET_NAME', None)
        explicit_production = getattr(settings, 'S3_PRODUCTION_BUCKET', None) or getattr(settings, 'AWS_PRODUCTION_BUCKET_NAME', None)

        if explicit_ingest or explicit_production:
            logger.debug(f"Legacy bucket mappings: ingest={self.ingest_bucket}, production={self.production_bucket}")

        # Skip bucket checks for external S3 - assume buckets exist
        # Only check buckets for local MinIO where we can create them
        if not skip_bucket_check and not self._buckets_checked and self.is_minio:
            # Only create buckets if specific buckets are listed (not "*")
            allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets) or not self.workspace_buckets
            
            if not allow_all:
                logger.info("Ensuring workspace buckets exist...")
                buckets_to_check = [b for b in self.workspace_buckets if b not in ("*", "__all__")]
                
                # Ensure all specified workspace buckets exist
                for bucket_name in buckets_to_check:
                    bucket_exists = self.ensure_bucket_exists(bucket_name)
                    if bucket_exists:
                        # Ensure CORS is configured for upload buckets (needed for direct uploads)
                        logger.info(f"Ensuring CORS is configured for {bucket_name}...")
                        cors_result = self.ensure_cors_enabled(bucket_name)
                        if cors_result["success"]:
                            if cors_result.get("updated", False):
                                logger.info(f"✅ CORS configuration for {bucket_name} has been updated")
                            else:
                                logger.info(f"✅ CORS configuration for {bucket_name} is already correct")
                        else:
                            logger.warning(f"⚠️ Failed to configure CORS for {bucket_name}: {cors_result.get('error', 'Unknown error')}")
            else:
                logger.info("All buckets mode enabled - skipping bucket creation checks (buckets will be discovered dynamically)")

            # Set the class-level flag
            self._buckets_checked = True
        elif not self.is_minio:
            logger.info("Skipping bucket checks for external S3 (buckets will be discovered dynamically)")
        
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
    
    def _get_ingest_bucket_name(self) -> Optional[str]:
        """
        Get the ingest bucket name for S3/MinIO.
        
        DEPRECATED: This is a legacy property. Use get_all_accessible_buckets() to get all buckets.
        Only returns a value if explicitly configured. Returns None otherwise.
        """
        # Check new-style setting first
        bucket_name = getattr(settings, 'S3_INGEST_BUCKET', None) or os.environ.get('S3_INGEST_BUCKET')
        if bucket_name:
            return bucket_name

        # Legacy fallback
        bucket_name = getattr(settings, 'AWS_INGEST_BUCKET_NAME', None) or os.environ.get('AWS_INGEST_BUCKET_NAME')
        if bucket_name:
            logger.debug("Using legacy AWS_INGEST_BUCKET_NAME setting")
            return bucket_name

        # Do NOT derive from workspace buckets - return None if not explicitly configured
        return None

    def _get_production_bucket_name(self) -> Optional[str]:
        """
        Get the production bucket name for S3/MinIO.
        
        DEPRECATED: This is a legacy property. Use get_all_accessible_buckets() to get all buckets.
        Only returns a value if explicitly configured. Returns None otherwise.
        """
        # Check new-style setting first
        bucket_name = getattr(settings, 'S3_PRODUCTION_BUCKET', None) or os.environ.get('S3_PRODUCTION_BUCKET')
        if bucket_name:
            return bucket_name

        # Legacy fallback
        bucket_name = getattr(settings, 'AWS_PRODUCTION_BUCKET_NAME', None) or os.environ.get('AWS_PRODUCTION_BUCKET_NAME')
        if bucket_name:
            logger.debug("Using legacy AWS_PRODUCTION_BUCKET_NAME setting")
            return bucket_name

        # Do NOT derive from workspace buckets - return None if not explicitly configured
        return None

    def _get_workspace_buckets(self) -> list:
        """Get the list of workspace buckets from settings."""
        workspace_buckets = getattr(settings, 'S3_WORKSPACE_BUCKETS', [])
        if isinstance(workspace_buckets, (list, tuple)):
            workspace_buckets = list(dict.fromkeys(str(bucket).strip() for bucket in workspace_buckets if bucket))
        elif isinstance(workspace_buckets, str):
            # Handle * or __all__ as wildcard for all buckets
            workspace_buckets_str = workspace_buckets.strip()
            if workspace_buckets_str in ("*", "__all__", ""):
                workspace_buckets = ["*"]  # Use * as marker for "all buckets"
            else:
                # Split comma-separated list
                workspace_buckets = [b.strip() for b in workspace_buckets_str.split(",") if b.strip()]
        else:
            workspace_buckets = []

        logger.info("Loaded workspace buckets from settings: %s", workspace_buckets)
        return workspace_buckets

    @property
    def ocfl_buckets(self) -> list:
        """
        Get all accessible buckets as OCFL-capable buckets.
        
        Note: This property triggers lazy loading when first accessed.
        All buckets are OCFL-capable.
        """
        return self.get_all_accessible_buckets()

    def is_ocfl_bucket(self, bucket_name: str) -> bool:
        """Check if a bucket allows OCFL operations. All buckets are OCFL-capable."""
        return True

    def _lazy_fetch_buckets(self) -> Generator[str, None, None]:
        """
        Lazy generator that yields buckets one at a time.
        Only fetches from S3 when iterated, not on call.
        
        Returns:
            Generator[str, None, None]: Lazy iterator yielding bucket names
        """
        # Check if we should allow all buckets
        allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets)
        allow_all = allow_all or not self.workspace_buckets  # Empty list also means all buckets

        if not allow_all:
            # If specific buckets are configured, yield only those (no S3 call needed)
            allowlist = [bucket for bucket in self.workspace_buckets if bucket not in ("*", "__all__")]
            allowlist = list(dict.fromkeys(allowlist))
            
            if allowlist and not self.is_minio:
                # For external S3 with allowlist, verify buckets exist as we yield them
                for bucket_name in allowlist:
                    try:
                        # Lazy check: only verify bucket exists when yielding
                        self.s3_client.head_bucket(Bucket=bucket_name)
                        yield bucket_name
                    except ClientError:
                        logger.debug("Bucket '%s' not accessible, skipping", bucket_name)
                return
            elif allowlist:
                # For MinIO with allowlist, just yield them
                yield from allowlist
                return

        # For "all buckets" mode, fetch lazily from S3
        try:
            response = self.s3_client.list_buckets()
            all_bucket_names = sorted(bucket['Name'] for bucket in response['Buckets'])
            logger.debug("📦 BUCKETS: Lazy fetch found %s buckets", len(all_bucket_names))
            
            for bucket_name in all_bucket_names:
                yield bucket_name
        except Exception as e:
            logger.exception("❌ Error listing buckets lazily: %s", e)
            # Fallback: yield workspace buckets if configured
            if self.workspace_buckets and self.workspace_buckets != ["*"]:
                for b in self.workspace_buckets:
                    if b not in ("*", "__all__"):
                        yield b

    def get_all_accessible_buckets(self) -> list:
        """
        Get all accessible buckets dynamically from S3/MinIO.
        
        This method uses lazy loading - buckets are only fetched when this method is called,
        not during service initialization. Use iter_buckets() for true lazy iteration.
        
        Returns:
            list: List of accessible bucket names
        """
        # Check cache first
        cache_key = "storage:bucket-names"
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug("Returning cached bucket list: %s", cached)
            return cached

        # Lazy fetch and cache the result
        try:
            bucket_names = list(self._lazy_fetch_buckets())
            
            # Check if we should allow all buckets (for logging)
            allow_all = any(bucket in ("*", "__all__") for bucket in self.workspace_buckets)
            allow_all = allow_all or not self.workspace_buckets
            
            if allow_all:
                logger.info("📦 BUCKETS: All buckets mode enabled, found %s buckets", len(bucket_names))
            else:
                logger.info("📦 BUCKETS: Found %s accessible buckets (filtered)", len(bucket_names))
            
            # Cache for a short time to avoid repeated calls, but keep it short for freshness
            cache.set(cache_key, bucket_names, timeout=60)  # Reduced from 300 to 60 seconds
            return bucket_names
        except Exception as e:
            logger.exception("❌ Error getting buckets: %s", e)
            # Fallback: return workspace buckets if configured, otherwise empty list
            if self.workspace_buckets and self.workspace_buckets != ["*"]:
                return [b for b in self.workspace_buckets if b not in ("*", "__all__")]
            return []

    def iter_buckets(self) -> Generator[str, None, None]:
        """
        Return a lazy iterator over accessible buckets.
        Buckets are fetched from S3 only when iterated, not on call.
        
        Use this when you only need to iterate through buckets and don't need a list.
        
        Example:
            for bucket in service.iter_buckets():
                process(bucket)
        
        Returns:
            Generator[str, None, None]: Lazy iterator yielding bucket names
        """
        return self._lazy_fetch_buckets()

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
        
        # Add region if specified
        if self.region:
            client_kwargs['region_name'] = self.region
        
        # Add endpoint URL for MinIO or custom S3 endpoints
        if self.endpoint_url:
            # For server-side operations, use the original endpoint URL
            server_endpoint = self.endpoint_url
            client_kwargs['endpoint_url'] = server_endpoint

            # For any custom endpoint (MinIO or S3-compatible), use path-style addressing
            # This prevents boto3 from trying virtual-hosted-style URLs like https://bucket.endpoint.com
            client_kwargs['config'] = boto3.session.Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )

            # For MinIO in local development, we need special handling for presigned URLs
            if self.is_minio:
                # Create a config that tells boto3 to use path-style addressing
                # This is required for MinIO
                client_kwargs['config'] = boto3.session.Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'path'}
                )
                
                # For presigned URLs that will be used by the browser,
                # we need to use a browser-accessible URL
                browser_endpoint = os.environ.get('AWS_S3_BROWSER_ENDPOINT_URL', None)
                
                if browser_endpoint:
                    logger.info(f"Using browser endpoint URL from environment: {browser_endpoint}")
                elif 'minio:9000' in self.endpoint_url:
                    # Default fallback for local development
                    browser_endpoint = self.endpoint_url.replace('minio:9000', 'localhost:9000')
                    logger.info(f"MinIO detected at {self.endpoint_url}, will use {browser_endpoint} for presigned URLs")
                else:
                    # If no specific browser endpoint is provided, use the same as server
                    browser_endpoint = self.endpoint_url
                    logger.info(f"Using server endpoint for presigned URLs: {browser_endpoint}")
                
                # Create a separate client for generating presigned URLs
                self.presigned_client = boto3.client(
                    's3',
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region if self.region else None,
                    endpoint_url=browser_endpoint,
                    config=boto3.session.Config(
                        signature_version='s3v4',
                        s3={'addressing_style': 'path'}
                    )
                )
                logger.info(f"Created separate client for presigned URLs with endpoint: {browser_endpoint}")
        
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
        logger.info(f"Checking if bucket '{bucket_name}' exists...")
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"✅ Bucket '{bucket_name}' already exists")
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            logger.info(f"Bucket check result: {error_code} - {error_message}")
            
            # If bucket doesn't exist, create it
            if error_code == '404' or error_code == 'NoSuchBucket':
                try:
                    logger.info(f"🔄 Creating bucket '{bucket_name}' in region '{self.region}'...")
                    if self.region == 'us-east-1':
                        # Special case for us-east-1
                        logger.info(f"Using special case for us-east-1 region (no LocationConstraint)")
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        logger.info(f"Using LocationConstraint={self.region}")
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"✅ Bucket '{bucket_name}' created successfully")
                    return True
                except Exception as create_error:
                    logger.error(f"❌ Error creating bucket '{bucket_name}': {str(create_error)}")
                    # Log more details about the error
                    if hasattr(create_error, 'response'):
                        error_details = create_error.response.get('Error', {})
                        logger.error(f"Error details: Code={error_details.get('Code')}, Message={error_details.get('Message')}")
                    return False
            else:
                logger.error(f"❌ Error checking bucket '{bucket_name}': {error_code} - {error_message}")
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
                "bucket_name": bucket_name,
                "path": file_path,
            }
        except ClientError as e:
            logger.error(f"Error getting file content for {file_path}: {str(e)}")
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
                    logger.info(f"Deleting {len(objects_to_delete)} objects from {bucket_name}/{object_path}")
                    deleted_count = 0
                    for obj in objects_to_delete:
                        try:
                            self.s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])
                            deleted_count += 1
                        except Exception as obj_error:
                            logger.error(f"Error deleting object {obj['Key']}: {str(obj_error)}")
                    
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
            logger.error(f"Error deleting {object_path}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def ensure_cors_enabled(self, bucket_name: str) -> Dict[str, Any]:
        """
        Ensure CORS is properly configured for the specified bucket.
        
        This is required for browser-based uploads to work properly.
        
        Args:
            bucket_name (str): Name of the bucket to configure.
        
        Returns:
            Dict[str, Any]: Result of the operation
        """
        if not bucket_name:
            return {"success": False, "error": "Bucket name is required"}
        
        logger.info(f"Checking CORS configuration for bucket: {bucket_name}")
        
        try:
            # Define the required CORS rule - using the exact minimal configuration provided
            required_rule = {
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['POST'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': []
            }
            
            # Check if CORS is already configured
            try:
                cors_config = self.s3_client.get_bucket_cors(Bucket=bucket_name)
                current_rules = cors_config.get('CORSRules', [])
                logger.info(f"Found existing CORS configuration with {len(current_rules)} rules")
                
                # Check if our required rule already exists
                rule_exists = False
                for rule in current_rules:
                    # Check if all required keys are in the existing rule
                    if (set(rule.get('AllowedHeaders', [])) >= set(required_rule['AllowedHeaders']) and
                        set(rule.get('AllowedMethods', [])) >= set(required_rule['AllowedMethods']) and
                        set(rule.get('AllowedOrigins', [])) >= set(required_rule['AllowedOrigins'])):
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
                    logger.error(f"❌ Error getting CORS configuration: {error_code} - {error_message}")
                    return {"success": False, "error": f"{error_code}: {error_message}"}
        
        except Exception as e:
            logger.error(f"❌ Error ensuring CORS configuration: {str(e)}")
            
            # For MinIO, CORS might not be fully supported, but uploads might still work
            if self.is_minio:
                logger.warning("⚠️ CORS configuration failed, but this is expected with some MinIO versions")
                logger.warning("⚠️ Browser uploads may still work despite this error")
                return {"success": True, "message": "CORS configuration skipped for MinIO", "updated": False}
            
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
