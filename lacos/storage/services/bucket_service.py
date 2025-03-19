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
    
    def __init__(self):
        """Initialize the BucketService with all required sub-services."""
        super().__init__()
        
        # Initialize the specialized services
        self.collection_service = CollectionService()
        self.upload_service = UploadService()
        
        # Configure child services with consistent settings
        self.set_client_and_buckets(self.collection_service)
        self.set_client_and_buckets(self.upload_service)
        
        # Initialize OCFL service after other services are ready
        self.ocfl_service = OCFLService(self)
        # OCFL service uses this instance's bucket references, so just set the client
        if hasattr(self.ocfl_service, 's3_client'):
            self.ocfl_service.s3_client = self.s3_client
        
        # Ensure both buckets exist
        logger.info("Ensuring buckets exist...")
        ingest_result = self.ensure_bucket_exists(self.ingest_bucket)
        production_result = self.ensure_bucket_exists(self.production_bucket)
        
        if ingest_result and production_result:
            logger.info("✅ All buckets are ready")
        else:
            logger.warning("⚠️ Some buckets could not be created or accessed")
            if not ingest_result:
                logger.warning(f"⚠️ Ingest bucket '{self.ingest_bucket}' is not available")
            if not production_result:
                logger.warning(f"⚠️ Production bucket '{self.production_bucket}' is not available")
        
        logger.info("BucketService initialized")
    
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
    
    # Upload-related methods
    def upload_folder_to_bucket(self, local_folder_path: str, bucket_name: str = None, target_prefix: str = "") -> Dict[str, Any]:
        """Delegate to upload service to upload a folder to a bucket."""
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        return self.upload_service.upload_folder_to_bucket(local_folder_path, bucket_name, target_prefix)
    
    def upload_files_directly(self, files, folder_name: str, bucket_name: str = None, file_paths: dict = None) -> Dict[str, Any]:
        """Delegate to upload service to upload files directly from a request."""
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        return self.upload_service.upload_files_directly(files, folder_name, bucket_name, file_paths)
    
    # OCFL-related methods
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """Move a folder from the ingest bucket to the production bucket using the OCFL service."""
        logger.info(f"Starting move to production for {source_prefix}")
        return self.ocfl_service.move_to_production(source_prefix)
