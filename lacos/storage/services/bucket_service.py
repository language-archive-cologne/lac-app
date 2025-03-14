import logging
import os
from typing import Any, Dict, List
import shutil
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
import boto3

logger = logging.getLogger(__name__)


class BucketService:
    """
    Service for interacting with S3/MinIO buckets.
    
    This service handles both local development with MinIO and production with S3.
    It automatically detects the environment and configures the client accordingly.
    """
    
    def __init__(self):
        """
        Initialize the BucketService with S3 client.
        
        The service automatically detects whether to use MinIO (local development)
        or S3 (production) based on environment settings.
        """
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
        self.s3_client = self._create_s3_client()
        
        logger.info(f"BucketService initialized with {'MinIO' if self.is_minio else 'S3'}")
        logger.info(f"Using endpoint: {self.endpoint_url or 'default S3 endpoint'}")
        logger.info(f"Using ingest bucket: {self.ingest_bucket}")
        logger.info(f"Using production bucket: {self.production_bucket}")
    
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
        logger.info(f"Creating S3 client with endpoint URL: {self.endpoint_url}")
        
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
        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"Bucket {bucket_name} already exists")
            return True
        except ClientError as e:
            # If bucket doesn't exist, create it
            if e.response['Error']['Code'] == '404':
                try:
                    logger.info(f"Creating bucket {bucket_name}")
                    if self.region == 'us-east-1':
                        # Special case for us-east-1
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"Bucket {bucket_name} created successfully")
                    return True
                except Exception as create_error:
                    logger.error(f"Error creating bucket {bucket_name}: {str(create_error)}")
                    return False
            else:
                logger.error(f"Error checking bucket {bucket_name}: {str(e)}")
                return False
    
    def upload_folder_to_bucket(self, local_folder_path: str, bucket_name: str = None, target_prefix: str = "") -> Dict[str, Any]:
        """
        Upload a local folder and all its contents to the specified S3 bucket.
        
        Args:
            local_folder_path (str): The local path to the folder to upload
            bucket_name (str, optional): The name of the S3 bucket to upload to. Defaults to ingest bucket.
            target_prefix (str, optional): The prefix (path) in the bucket where the folder should be uploaded
            
        Returns:
            Dict[str, Any]: A dictionary containing the upload results
        """
        if bucket_name is None:
            bucket_name = self.ingest_bucket
            
        if not os.path.exists(local_folder_path):
            return {"success": False, "error": f"Local folder does not exist: {local_folder_path}"}
            
        if not os.path.isdir(local_folder_path):
            return {"success": False, "error": f"Path is not a directory: {local_folder_path}"}
        
        # Ensure the bucket exists
        if not self.ensure_bucket_exists(bucket_name):
            return {"success": False, "error": f"Failed to ensure bucket exists: {bucket_name}"}
        
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
                
            logger.info(f"Uploading folder {local_folder_path} to {bucket_name}/{full_prefix}")
            
            # Walk through the directory and upload all files
            for root, _, files in os.walk(local_folder_path):
                for file in files:
                    local_path = os.path.join(root, file)
                    
                    # Calculate the relative path from the base folder
                    rel_path = os.path.relpath(local_path, local_folder_path)
                    
                    # Create the S3 key (path in the bucket)
                    s3_key = f"{full_prefix}{rel_path}"
                    
                    try:
                        # Get file size
                        file_size = os.path.getsize(local_path)
                        total_size += file_size
                        
                        # Upload the file
                        logger.info(f"Uploading {local_path} to {bucket_name}/{s3_key}")
                        self.s3_client.upload_file(local_path, bucket_name, s3_key)
                        
                        uploaded_files.append({
                            "local_path": local_path,
                            "s3_key": s3_key,
                            "size": file_size,
                            "size_formatted": self._format_size(file_size)
                        })
                    except Exception as e:
                        logger.error(f"Error uploading {local_path}: {str(e)}")
                        failed_files.append({
                            "local_path": local_path,
                            "error": str(e)
                        })
            
            # Return the results
            return {
                "success": len(failed_files) == 0,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "target_prefix": full_prefix
            }
        except Exception as e:
            logger.error(f"Error uploading folder {local_folder_path}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def list_bucket_contents(self, bucket_name: str, prefix: str = "") -> List[Dict[str, any]]:
        """
        List the contents of a bucket with the given prefix.
        
        Args:
            bucket_name (str): The name of the bucket to list
            prefix (str, optional): The prefix (path) to list. Defaults to "".
            
        Returns:
            List[Dict[str, any]]: A list of dictionaries containing information about the objects
        """
        try:
            logger.info(
                f"Listing contents of bucket: '{bucket_name}' with prefix: '{prefix}'"
            )
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=prefix, Delimiter="/"
            )
            contents = []

            for obj in response.get("Contents", []):
                item = {
                    "name": os.path.basename(obj["Key"]),
                    "path": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                    "is_dir": False,
                }
                contents.append(item)
                logger.info(f"Found file: {item}")

            for prefix in response.get("CommonPrefixes", []):
                item = {
                    "name": os.path.basename(prefix["Prefix"].rstrip("/")),
                    "path": prefix["Prefix"],
                    "is_dir": True,
                }
                contents.append(item)
                logger.info(f"Found directory: {item}")

            return contents
        except ClientError as e:
            logger.error(
                f"Error listing bucket contents for bucket: '{bucket_name}'. Error: {e}"
            )
            return []
    
    def get_folder_structure(self, bucket_name: str, prefix: str = "") -> List[Dict[str, any]]:
        """
        Get a hierarchical folder structure starting from the given prefix in the specified bucket.

        Args:
            bucket_name (str): The name of the bucket to get the structure from
            prefix (str, optional): The starting prefix (folder) to build the structure from. Defaults to "".
            
        Returns:
            List[Dict[str, any]]: List of dictionaries representing the folder structure
        """
        contents = self.list_bucket_contents(bucket_name, prefix)
        structure = []
        for item in contents:
            if item["is_dir"]:
                # For directories, recursively get their contents
                item["children"] = self.get_folder_structure(
                    bucket_name, item["path"]
                )
            structure.append(item)
        logger.info(
            f"Fetched folder structure for {bucket_name} with prefix {prefix}: {structure}"
        )
        return structure
    
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
    
    def is_ocfl_object(self, bucket_name: str, prefix: str) -> bool:
        """
        Check if the given prefix in the bucket is an OCFL object.
        
        Args:
            bucket_name (str): The name of the bucket to check
            prefix (str): The prefix (path) to check
            
        Returns:
            bool: True if the prefix is an OCFL object, False otherwise
        """
        try:
            # List objects with the given prefix
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=prefix
            )
            
            # Check if any of the objects have the OCFL version marker
            for obj in response.get("Contents", []):
                if os.path.basename(obj["Key"]).startswith("0=ocfl_object_"):
                    return True
            
            return False
        except ClientError as e:
            logger.error(f"Error checking if {prefix} is an OCFL object: {str(e)}")
            return False
    
    def find_ocfl_objects(self, bucket_name: str, prefix: str = "") -> List[str]:
        """
        Find all OCFL objects in the given bucket and prefix.
        
        Args:
            bucket_name (str): The name of the bucket to search
            prefix (str, optional): The prefix (path) to search. Defaults to "".
            
        Returns:
            List[str]: A list of prefixes (paths) that are OCFL objects
        """
        ocfl_objects = []
        
        try:
            # List all objects in the bucket with the given prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")
            
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    # Check if the object is an OCFL version marker
                    if os.path.basename(obj["Key"]).startswith("0=ocfl_object_"):
                        # Get the directory containing the marker
                        dir_path = os.path.dirname(obj["Key"])
                        if dir_path not in ocfl_objects:
                            ocfl_objects.append(dir_path)
            
            return ocfl_objects
        except ClientError as e:
            logger.error(f"Error finding OCFL objects: {str(e)}")
            return []
    
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """
        Move an OCFL object from the ingest bucket to the production bucket.
        This involves standardizing the OCFL structure according to the requirements.
        
        Args:
            source_prefix (str): The prefix (path) of the OCFL object in the ingest bucket
            
        Returns:
            Dict[str, Any]: A dictionary containing the result of the operation
        """
        # Check if the source is an OCFL object
        if not self.is_ocfl_object(self.ingest_bucket, source_prefix):
            return {
                "success": False, 
                "error": f"Source {source_prefix} is not an OCFL object"
            }
        
        try:
            # Create a temporary directory to download the object
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the object
                self._download_directory(self.ingest_bucket, source_prefix, temp_dir)
                
                # Standardize the OCFL structure
                # This would typically call a function similar to standardize_ocfl_structure
                # For now, we'll just upload the object as-is to the production bucket
                result = self._upload_directory(temp_dir, self.production_bucket, source_prefix)
                
                if result["success"]:
                    return {
                        "success": True,
                        "message": f"Successfully moved {source_prefix} to production bucket",
                        "source_bucket": self.ingest_bucket,
                        "source_prefix": source_prefix,
                        "target_bucket": self.production_bucket,
                        "target_prefix": source_prefix,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to upload to production bucket: {result.get('error', 'Unknown error')}",
                    }
        except Exception as e:
            logger.error(f"Error moving {source_prefix} to production: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _download_directory(self, bucket_name: str, prefix: str, local_dir: str) -> None:
        """
        Download a directory from S3 to a local directory.
        
        Args:
            bucket_name (str): The name of the bucket to download from
            prefix (str): The prefix (path) to download
            local_dir (str): The local directory to download to
        """
        try:
            # List all objects with the given prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")
            
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    # Get the relative path from the prefix
                    rel_path = obj["Key"][len(prefix):].lstrip("/")
                    
                    # Create the local path
                    local_path = os.path.join(local_dir, rel_path)
                    
                    # Create the directory if it doesn't exist
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    
                    # Download the file
                    self.s3_client.download_file(bucket_name, obj["Key"], local_path)
                    logger.info(f"Downloaded {obj['Key']} to {local_path}")
        except ClientError as e:
            logger.error(f"Error downloading directory {prefix}: {str(e)}")
            raise
    
    def _upload_directory(self, local_dir: str, bucket_name: str, target_prefix: str) -> Dict[str, Any]:
        """
        Upload a local directory to S3.
        
        Args:
            local_dir (str): The local directory to upload
            bucket_name (str): The name of the bucket to upload to
            target_prefix (str): The prefix (path) in the bucket to upload to
            
        Returns:
            Dict[str, Any]: A dictionary containing the result of the operation
        """
        try:
            uploaded_files = []
            failed_files = []
            total_size = 0
            
            # Walk through the directory and upload all files
            for root, _, files in os.walk(local_dir):
                for file in files:
                    local_path = os.path.join(root, file)
                    
                    # Calculate the relative path from the local directory
                    rel_path = os.path.relpath(local_path, local_dir)
                    
                    # Create the S3 key (path in the bucket)
                    s3_key = f"{target_prefix.rstrip('/')}/{rel_path}"
                    
                    try:
                        # Get file size
                        file_size = os.path.getsize(local_path)
                        total_size += file_size
                        
                        # Upload the file
                        self.s3_client.upload_file(local_path, bucket_name, s3_key)
                        
                        uploaded_files.append({
                            "local_path": local_path,
                            "s3_key": s3_key,
                            "size": file_size,
                            "size_formatted": self._format_size(file_size)
                        })
                    except Exception as e:
                        logger.error(f"Error uploading {local_path}: {str(e)}")
                        failed_files.append({
                            "local_path": local_path,
                            "error": str(e)
                        })
            
            # Return the results
            return {
                "success": len(failed_files) == 0,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "target_prefix": target_prefix
            }
        except Exception as e:
            logger.error(f"Error uploading directory {local_dir}: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
                    # Delete the objects
                    self.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": objects_to_delete}
                    )
                    
                    return {
                        "success": True,
                        "message": f"Successfully deleted directory {object_path} with {len(objects_to_delete)} objects",
                        "deleted_objects": len(objects_to_delete)
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
