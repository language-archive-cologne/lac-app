import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

class OCFLService:
    """
    Service for handling OCFL (Oxford Common File Layout) operations.
    This service provides methods for validating and standardizing OCFL structures.
    """
    
    def __init__(self, bucket_service):
        """
        Initialize the OCFL service.
        
        Args:
            bucket_service: An instance of BucketService for S3 operations
        """
        self.bucket_service = bucket_service
        self.ingest_bucket = bucket_service.ingest_bucket
        self.production_bucket = bucket_service.production_bucket
    
    def validate_structure(self, source_prefix: str) -> Dict[str, Any]:
        """
        Validate if a directory in the ingest bucket has a valid OCFL structure.
        
        Args:
            source_prefix (str): The path in the ingest bucket to validate
            
        Returns:
            Dict[str, Any]: Result of the validation
        """
        logger.info(f"Validating OCFL structure for {source_prefix}")
        
        try:
            # Check if source exists in ingest bucket
            contents = self.bucket_service.list_bucket_contents(self.ingest_bucket, source_prefix)
            if not contents:
                return {
                    "success": False,
                    "error": f"Source {source_prefix} not found in ingest bucket"
                }
            
            # Check for OCFL version marker
            has_version_marker = False
            has_content_dir = False
            has_xml_files = False
            
            for item in contents:
                if item.get("is_dir", False):
                    if item["name"].startswith("0=ocfl_object_"):
                        has_version_marker = True
                    elif item["name"] == "v1":
                        has_content_dir = True
                elif item["name"].endswith(".xml"):
                    has_xml_files = True
            
            if not has_version_marker:
                return {
                    "success": False,
                    "error": "No OCFL version marker found",
                    "needs_transform": True
                }
            
            if not has_content_dir:
                return {
                    "success": False,
                    "error": "No v1/content directory found",
                    "needs_transform": True
                }
            
            if not has_xml_files:
                return {
                    "success": False,
                    "error": "No XML files found in content directory",
                    "needs_transform": True
                }
            
            return {
                "success": True,
                "message": "Valid OCFL structure found",
                "needs_transform": False
            }
            
        except Exception as e:
            logger.error(f"Error validating OCFL structure: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def transform_structure(self, source_prefix: str) -> Dict[str, Any]:
        """
        Transform a directory to follow OCFL structure.
        
        Args:
            source_prefix (str): The path in the ingest bucket to transform
            
        Returns:
            Dict[str, Any]: Result of the transformation
        """
        logger.info(f"Transforming structure for {source_prefix}")
        
        try:
            # Create temporary directory for transformation
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download source to temp directory
                self.bucket_service._download_directory(self.ingest_bucket, source_prefix, temp_dir)
                
                # Create OCFL structure
                ocfl_dir = os.path.join(temp_dir, "ocfl_object")
                os.makedirs(ocfl_dir, exist_ok=True)
                
                # Create version marker
                version_marker = "0=ocfl_object_1.0"
                with open(os.path.join(ocfl_dir, version_marker), "w") as f:
                    f.write("")
                
                # Create v1 directory
                v1_dir = os.path.join(ocfl_dir, "v1")
                os.makedirs(v1_dir, exist_ok=True)
                
                # Move files to appropriate locations
                source_dir = os.path.join(temp_dir, os.path.basename(source_prefix))
                if os.path.exists(source_dir):
                    # Move XML files to metadata
                    metadata_dir = os.path.join(v1_dir, "metadata")
                    os.makedirs(metadata_dir, exist_ok=True)
                    
                    for root, _, files in os.walk(source_dir):
                        for file in files:
                            if file.endswith(".xml"):
                                src = os.path.join(root, file)
                                dst = os.path.join(metadata_dir, file)
                                shutil.move(src, dst)
                    
                    # Move acl.json if exists
                    acl_file = os.path.join(source_dir, "acl.json")
                    if os.path.exists(acl_file):
                        shutil.move(acl_file, os.path.join(metadata_dir, "acl.json"))
                    
                    # Handle Resources directory
                    resources_dir = os.path.join(source_dir, "Resources")
                    if os.path.exists(resources_dir):
                        content_dir = os.path.join(v1_dir, "content")
                        os.makedirs(content_dir, exist_ok=True)
                        shutil.move(resources_dir, content_dir)
                
                # Upload transformed structure to production
                result = self.bucket_service._upload_directory(
                    ocfl_dir,
                    self.production_bucket,
                    source_prefix
                )
                
                if result["success"]:
                    return {
                        "success": True,
                        "message": "Successfully transformed and moved to production",
                        "details": result
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to upload transformed structure",
                        "details": result
                    }
                
        except Exception as e:
            logger.error(f"Error transforming structure: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """
        Move a folder from ingest to production, ensuring OCFL structure.
        
        Args:
            source_prefix (str): The path in the ingest bucket to move
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        logger.info(f"Starting move to production for {source_prefix}")
        
        try:
            # First validate the structure
            validation_result = self.validate_structure(source_prefix)
            
            if not validation_result["success"]:
                if validation_result.get("needs_transform", False):
                    # Structure needs transformation
                    return self.transform_structure(source_prefix)
                else:
                    return validation_result
            
            # Structure is valid, copy directly
            try:
                # List all objects in the source
                paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")
                
                for page in paginator.paginate(Bucket=self.ingest_bucket, Prefix=source_prefix):
                    for obj in page.get("Contents", []):
                        # Copy each object to production
                        self.bucket_service.s3_client.copy_object(
                            CopySource={"Bucket": self.ingest_bucket, "Key": obj["Key"]},
                            Bucket=self.production_bucket,
                            Key=obj["Key"]
                        )
                
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to production bucket"
                }
                
            except Exception as copy_error:
                logger.error(f"Error copying to production: {str(copy_error)}")
                return {
                    "success": False,
                    "error": f"Failed to copy to production: {str(copy_error)}"
                }
                
        except Exception as e:
            logger.error(f"Error in move_to_production: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 