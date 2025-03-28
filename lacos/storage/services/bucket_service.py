import logging
import os
from typing import Any, Dict, List
import shutil
import tempfile
from pathlib import Path
import time

from botocore.exceptions import ClientError
from django.conf import settings
import boto3
from django.core.management import call_command
from io import StringIO
import sys

from .base_storage_service import BaseStorageService
from .collection_service import CollectionService
from .upload_service import UploadService
from .ocfl_service import OCFLService

logger = logging.getLogger(__name__)


class BucketService(BaseStorageService):
    """
    Primary service for interacting with S3/MinIO buckets.
    
    This service delegates to specialized services for specific functionality
    while providing a unified interface for the application.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BucketService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the BucketService with all required sub-services.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        
        # Initialize the specialized services with skip_bucket_check=True
        self.collection_service = CollectionService(skip_bucket_check=True)
        self.upload_service = UploadService(skip_bucket_check=True)
        
        # Configure child services with consistent settings
        self.set_client_and_buckets(self.collection_service)
        self.set_client_and_buckets(self.upload_service)
        
        # Initialize OCFL service after other services are ready
        self.ocfl_service = OCFLService(self)
        # OCFL service uses this instance's bucket references, so just set the client
        if hasattr(self.ocfl_service, 's3_client'):
            self.ocfl_service.s3_client = self.s3_client
        
        logger.info("BucketService initialized")
        self.initialized = True
    
    def get_root_level_items(self, bucket_name: str) -> Dict[str, Any]:
        """
        Get only the root level items (files and folders) from a bucket.
        This is optimized for the initial dashboard load.
        
        Args:
            bucket_name (str): The name of the bucket to list
            
        Returns:
            Dict[str, Any]: Dictionary containing root level items
        """
        try:
            contents = self.collection_service.list_bucket_contents(bucket_name)
            
            # Transform the contents into the expected structure
            return {
                "type": "folder",
                "name": bucket_name,
                "path": "",
                "children": [
                    {
                        "type": "folder" if item["is_dir"] else "file",
                        "name": item["name"],
                        "path": item["path"],
                        "size": item.get("size"),
                        "last_modified": item.get("last_modified"),
                    }
                    for item in contents
                ]
            }
        except Exception as e:
            logger.error(f"Error getting root level items for bucket '{bucket_name}': {str(e)}")
            return {"type": "folder", "name": bucket_name, "path": "", "children": []}
    
    def get_folder_contents(self, bucket_name: str, folder_path: str) -> List[Dict[str, Any]]:
        """
        Get the contents of a specific folder.
        This is used for lazy loading folder contents.
        
        Args:
            bucket_name (str): The name of the bucket
            folder_path (str): The path to the folder
            
        Returns:
            List[Dict[str, Any]]: List of items in the folder
        """
        try:
            contents = self.collection_service.list_bucket_contents(bucket_name, folder_path)
            
            # Transform the contents into the expected structure
            return [
                {
                    "type": "folder" if item["is_dir"] else "file",
                    "name": item["name"],
                    "path": item["path"],
                    "size": item.get("size"),
                    "last_modified": item.get("last_modified"),
                }
                for item in contents
            ]
        except Exception as e:
            logger.error(f"Error getting folder contents for '{folder_path}' in bucket '{bucket_name}': {str(e)}")
            return []
    
    # Collection-related methods
    def is_collection_path(self, path: str) -> bool:
        """Delegate to collection service to check if a path is a collection."""
        return self.collection_service.is_collection_path(path)
    
    def get_collection_parent_path(self, path: str) -> str:
        """Delegate to collection service to get the parent path of a collection."""
        return self.collection_service.get_collection_parent_path(path)
    
    def is_ocfl_object(self, bucket_name: str, prefix: str) -> bool:
        """Delegate to collection service to check if a path is an OCFL object."""
        return self.collection_service.is_ocfl_object(bucket_name, prefix)
    
    def find_ocfl_objects(self, bucket_name: str, prefix: str = "") -> List[str]:
        """Delegate to collection service to find all OCFL objects in a bucket/prefix."""
        return self.collection_service.find_ocfl_objects(bucket_name, prefix)
    
    def list_bucket_contents(self, bucket_name: str, prefix: str = "") -> List[Dict[str, any]]:
        """Delegate to collection service to list bucket contents."""
        return self.collection_service.list_bucket_contents(bucket_name, prefix)
    
    def get_folder_structure(self, bucket_name: str, prefix: str = "") -> Dict[str, Any]:
        """Delegate to collection service to get folder structure."""
        return self.collection_service.get_folder_structure(bucket_name, prefix)
    
    
    # OCFL-related methods
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """Move a folder from the ingest bucket to the production bucket using the OCFL service."""
        logger.info(f"Starting move to production for {source_prefix}")
        return self.ocfl_service.move_to_production(source_prefix)
        
    def direct_move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """
        Move a folder from the ingest bucket to the production bucket directly without any transformation.
        This bypasses the OCFL service completely and just copies the files as they are.
        
        Args:
            source_prefix (str): The path in the ingest bucket to move
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        logger.info(f"Starting direct move to production for {source_prefix}")
        
        try:
            # Verify ingest and production buckets are different
            if self.ingest_bucket == self.production_bucket:
                error_message = "Error: Ingest and production buckets must be different"
                logger.error(error_message)
                return {
                    "success": False,
                    "error": error_message
                }
            
            # Ensure source_prefix ends with a slash for proper prefix matching
            if not source_prefix.endswith('/'):
                source_prefix = source_prefix + '/'
                logger.info(f"Added trailing slash for proper prefix matching: {source_prefix}")
            
            # List all objects in the source
            paginator = self.s3_client.get_paginator("list_objects_v2")
            copied_files = 0
            
            for page in paginator.paginate(Bucket=self.ingest_bucket, Prefix=source_prefix):
                for obj in page.get("Contents", []):
                    source_key = obj["Key"]
                    
                    # Skip if this is just the folder marker object
                    if source_key == source_prefix:
                        logger.info(f"Skipping folder marker object: {source_key}")
                        continue
                    
                    # Copy the object to the production bucket
                    self.s3_client.copy_object(
                        CopySource={"Bucket": self.ingest_bucket, "Key": source_key},
                        Bucket=self.production_bucket,
                        Key=source_key
                    )
                    
                    copied_files += 1
                    
                    if copied_files % 10 == 0:
                        logger.info(f"Copied {copied_files} files so far...")
            
            # Add an empty directory marker if no files were found
            if copied_files == 0:
                logger.warning(f"No files found to copy, creating an empty directory marker: {source_prefix}")
                self.s3_client.put_object(
                    Bucket=self.production_bucket,
                    Key=source_prefix,
                    Body=''
                )
                copied_files = 1
            
            if copied_files > 0:
                logger.info(f"Successfully copied {copied_files} files from {source_prefix} to production bucket")
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to production bucket ({copied_files} files copied)"
                }
            else:
                # This should never happen now due to the empty directory marker
                logger.warning(f"No files found to copy at {source_prefix}")
                return {
                    "success": False,
                    "error": f"No files found to copy at {source_prefix}"
                }
                
        except Exception as e:
            logger.error(f"Error in direct_move_to_production: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def delete_folder(self, bucket_name, folder_path):
        """
        Delete a folder and all its contents from the specified bucket.
        
        Args:
            bucket_name: The name of the bucket
            folder_path: Path to the folder to delete
        
        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self.delete_object(bucket_name, folder_path, is_directory=True)
        
    def delete_file(self, bucket_name, file_path):
        """
        Delete a single file from the specified bucket.
        
        Args:
            bucket_name: The name of the bucket
            file_path: Path to the file to delete
        
        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self.delete_object(bucket_name, file_path, is_directory=False)

