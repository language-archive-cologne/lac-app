import logging
import os
from typing import Any, Dict
import boto3
from botocore.exceptions import ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

class BaseStorageService:
    """
    Base service for interacting with S3/MinIO storage.
    
    This service handles both local development with MinIO and production with S3.
    It automatically detects the environment and configures the client accordingly.
    """
    
    def __init__(self):
        """
        Initialize the BaseStorageService with S3 client.
        
        The service automatically detects whether to use MinIO (local development)
        or S3 (production) based on environment settings.
        """
        logger.info("Initializing BaseStorageService...")
        
        # Initialize settings
        self.is_minio = self._is_minio_environment()
        self.endpoint_url = self._get_endpoint_url()
        self.access_key = self._get_access_key()
        self.secret_key = self._get_secret_key()
        self.region = self._get_region()
        
        # Initialize both buckets
        self.ingest_bucket = self._get_ingest_bucket_name()
        self.production_bucket = self._get_production_bucket_name()
        
        # Create S3 client
        logger.info(f"Creating S3 client with endpoint URL: {self.endpoint_url}")
        self.s3_client = self._create_s3_client()
        
        logger.info(f"BaseStorageService initialized with {'MinIO' if self.is_minio else 'S3'}")
        logger.info(f"Using endpoint: {self.endpoint_url or 'default S3 endpoint'}")
        logger.info(f"Using region: {self.region}")
        logger.info(f"Using ingest bucket: {self.ingest_bucket}")
        logger.info(f"Using production bucket: {self.production_bucket}")
    
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
        
        # Default bucket name
        if self._is_minio_environment():
            return 'lacos-production'
        
        # For production, we should have a setting or environment variable
        logger.warning("No AWS_PRODUCTION_BUCKET_NAME found in settings or environment")
        return 'lacos-production'
    
    def _create_s3_client(self):
        """Create an S3 client based on the settings."""
        session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

        return session.client(
            "s3",
            endpoint_url=self.endpoint_url if self.is_minio else None,
            use_ssl=not self.is_minio,
        )
    
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
                "bucket_type": "ingest" if bucket_name == self.ingest_bucket else "production",
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