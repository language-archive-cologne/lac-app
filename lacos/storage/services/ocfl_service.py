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
                
                # Log the directory structure for debugging
                logger.info(f"Downloaded content to {temp_dir}")
                self._log_directory_structure(temp_dir)
                
                # Create OCFL structure in a new directory
                ocfl_dir = os.path.join(temp_dir, "ocfl_object")
                os.makedirs(ocfl_dir, exist_ok=True)
                
                # Create version marker
                version_marker = "0=ocfl_object_1.0"
                with open(os.path.join(ocfl_dir, version_marker), "w") as f:
                    f.write("")
                
                # Create v1 directory and content/metadata subdirectories
                v1_dir = os.path.join(ocfl_dir, "v1")
                content_dir = os.path.join(v1_dir, "content")
                metadata_dir = os.path.join(v1_dir, "content", "metadata")
                os.makedirs(metadata_dir, exist_ok=True)
                
                # Find the actual source directory - search for it rather than assuming a fixed path
                source_dir = self._find_source_directory(temp_dir, source_prefix)
                
                if source_dir and os.path.exists(source_dir):
                    logger.info(f"Found source directory at {source_dir}")
                    
                    # Find and move XML files to metadata
                    self._move_xml_files(source_dir, metadata_dir)
                    
                    # Find and move acl.json if it exists
                    self._move_acl_file(source_dir, metadata_dir)
                    
                    # Handle Resources directory if it exists
                    resources_dir = self._find_resources_directory(source_dir)
                    if resources_dir and os.path.exists(resources_dir):
                        logger.info(f"Found Resources directory at {resources_dir}")
                        dest_resources = os.path.join(content_dir, "Resources")
                        shutil.copytree(resources_dir, dest_resources)
                else:
                    logger.warning(f"Could not find source directory in {temp_dir}")
                
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
    
    def _log_directory_structure(self, directory: str) -> None:
        """Log the directory structure for debugging purposes"""
        logger.info(f"Directory structure of {directory}:")
        for root, dirs, files in os.walk(directory):
            rel_path = os.path.relpath(root, directory)
            if rel_path == ".":
                rel_path = ""
            logger.info(f"  Directory: {rel_path}")
            for file in files:
                logger.info(f"    File: {os.path.join(rel_path, file)}")
    
    def _find_source_directory(self, temp_dir: str, source_prefix: str) -> str:
        """
        Find the actual source directory based on the source_prefix.
        This handles cases where parent/child directory names might be identical.
        """
        # Extract the last part of the source_prefix
        parts = source_prefix.rstrip('/').split('/')
        if not parts:
            return temp_dir
            
        last_part = parts[-1]
        
        # First try direct path
        direct_path = os.path.join(temp_dir, last_part)
        if os.path.isdir(direct_path):
            return direct_path
            
        # If that doesn't work, try to find the directory by walking the temp_dir
        for root, dirs, _ in os.walk(temp_dir):
            if last_part in dirs:
                return os.path.join(root, last_part)
                
        # If all else fails, return the temp_dir itself
        return temp_dir
    
    def _move_xml_files(self, source_dir: str, metadata_dir: str) -> None:
        """Find and move all XML files to the metadata directory"""
        xml_files_moved = 0
        
        # First get the absolute path of the metadata directory to avoid processing it
        abs_metadata_dir = os.path.abspath(metadata_dir)
        
        for root, _, files in os.walk(source_dir):
            # Skip the metadata directory itself to avoid copying files to themselves
            if os.path.abspath(root).startswith(abs_metadata_dir):
                logger.info(f"Skipping metadata directory: {root}")
                continue
                
            for file in files:
                if file.endswith(".xml"):
                    src = os.path.join(root, file)
                    dst = os.path.join(metadata_dir, file)
                    
                    # Skip if destination already exists or source and destination are the same
                    if os.path.exists(dst) and os.path.samefile(src, dst):
                        logger.info(f"Skipping file that would copy to itself: {src}")
                        continue
                        
                    logger.info(f"Moving XML file from {src} to {dst}")
                    shutil.copy2(src, dst)
                    xml_files_moved += 1
                    
        logger.info(f"Moved {xml_files_moved} XML files to metadata directory")
    
    def _move_acl_file(self, source_dir: str, metadata_dir: str) -> None:
        """Find and move acl.json file to the metadata directory"""
        # Get the destination path
        dest_acl_file = os.path.join(metadata_dir, "acl.json")
        
        # First check if acl.json exists directly in the source directory
        acl_file = os.path.join(source_dir, "acl.json")
        if os.path.exists(acl_file):
            # Skip if source and destination are the same
            if os.path.exists(dest_acl_file) and os.path.samefile(acl_file, dest_acl_file):
                logger.info(f"Skipping acl.json that would copy to itself: {acl_file}")
            else:
                logger.info(f"Moving acl.json from {acl_file} to metadata directory")
                shutil.copy2(acl_file, dest_acl_file)
            return
            
        # Get the absolute path of the metadata directory to avoid processing it
        abs_metadata_dir = os.path.abspath(metadata_dir)
            
        # If not found, search for it recursively
        for root, _, files in os.walk(source_dir):
            # Skip the metadata directory itself
            if os.path.abspath(root).startswith(abs_metadata_dir):
                continue
                
            if "acl.json" in files:
                acl_file = os.path.join(root, "acl.json")
                
                # Skip if source and destination are the same
                if os.path.exists(dest_acl_file) and os.path.samefile(acl_file, dest_acl_file):
                    logger.info(f"Skipping acl.json that would copy to itself: {acl_file}")
                else:
                    logger.info(f"Found acl.json at {acl_file}, moving to metadata directory")
                    shutil.copy2(acl_file, dest_acl_file)
                return
                
        logger.warning("acl.json not found in source directory")
    
    def _find_resources_directory(self, source_dir: str) -> Optional[str]:
        """Find the Resources directory in the source directory"""
        # First check if Resources exists directly in the source directory
        resources_dir = os.path.join(source_dir, "Resources")
        if os.path.isdir(resources_dir):
            return resources_dir
            
        # If not found, search for it recursively
        for root, dirs, _ in os.walk(source_dir):
            if "Resources" in dirs:
                return os.path.join(root, "Resources")
                
        return None
    
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
                    logger.info(f"Structure needs transformation, transforming {source_prefix}")
                    return self.transform_structure(source_prefix)
                else:
                    logger.error(f"Validation failed: {validation_result.get('error', 'Unknown error')}")
                    return validation_result
            
            # Structure is valid, copy directly
            try:
                logger.info(f"Structure is valid, copying {source_prefix} directly to production")
                copied_files = 0
                
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
                        copied_files += 1
                
                logger.info(f"Successfully copied {copied_files} files from {source_prefix} to production bucket")
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to production bucket ({copied_files} files copied)"
                }
                
            except Exception as copy_error:
                logger.error(f"Error copying to production: {str(copy_error)}")
                # If direct copy failed, try transformation as a fallback
                logger.info(f"Direct copy failed, trying transformation as fallback")
                return self.transform_structure(source_prefix)
                
        except Exception as e:
            logger.error(f"Error in move_to_production: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 