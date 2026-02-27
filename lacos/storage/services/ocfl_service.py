import logging
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import uuid
import hashlib
import json

from botocore.exceptions import ClientError

from django.conf import settings

from lacos.storage.constants import OCFL_DATA_DIR

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
        logger.info("Validating OCFL structure", extra={"source_prefix": source_prefix})
        
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
            logger.error("Error validating OCFL structure", extra={"error": str(e)})
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
        logger.info("Transforming structure", extra={"source_prefix": source_prefix})
        
        try:
            # Create temporary directory for transformation
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download source to temp directory
                self.bucket_service._download_directory(self.ingest_bucket, source_prefix, temp_dir)
                
                # Log the directory structure for debugging
                logger.info("Downloaded content to temp directory", extra={"temp_dir": temp_dir})
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
                    logger.info("Found source directory", extra={"source_dir": source_dir})
                    
                    # Find and move XML files to metadata
                    self._move_xml_files(source_dir, metadata_dir)
                    
                    # Find and move acl.json if it exists
                    self._move_acl_file(source_dir, metadata_dir)
                    
                # Handle data directory if it exists
                data_dir = self._find_data_directory(source_dir)
                if data_dir and os.path.exists(data_dir):
                    logger.info("Found data directory", extra={"data_dir": data_dir})
                    dest_data = os.path.join(content_dir, OCFL_DATA_DIR)
                    shutil.copytree(data_dir, dest_data, dirs_exist_ok=True)
                else:
                    logger.warning("Could not find source directory", extra={"temp_dir": temp_dir})
                
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
            logger.error("Error transforming structure", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }
    
    def _log_directory_structure(self, directory: str) -> None:
        """Log the directory structure for debugging purposes"""
        logger.info("Directory structure", extra={"directory": directory})
        for root, dirs, files in os.walk(directory):
            rel_path = os.path.relpath(root, directory)
            if rel_path == ".":
                rel_path = ""
            logger.info("Directory entry", extra={"rel_path": rel_path})
            for file in files:
                logger.info("File entry", extra={"file_path": os.path.join(rel_path, file)})
    
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
                logger.info("Skipping metadata directory", extra={"root": root})
                continue
                
            for file in files:
                if file.endswith(".xml"):
                    src = os.path.join(root, file)
                    dst = os.path.join(metadata_dir, file)
                    
                    # Skip if destination already exists or source and destination are the same
                    if os.path.exists(dst) and os.path.samefile(src, dst):
                        logger.info("Skipping file that would copy to itself", extra={"src": src})
                        continue

                    logger.info("Moving XML file", extra={"src": src, "dst": dst})
                    shutil.copy2(src, dst)
                    xml_files_moved += 1
                    
        logger.info("Moved XML files to metadata directory", extra={"count": xml_files_moved})
    
    def _move_acl_file(self, source_dir: str, metadata_dir: str) -> None:
        """Find and move acl.json file to the metadata directory"""
        # Get the destination path
        dest_acl_file = os.path.join(metadata_dir, "acl.json")
        
        # First check if acl.json exists directly in the source directory
        acl_file = os.path.join(source_dir, "acl.json")
        if os.path.exists(acl_file):
            # Skip if source and destination are the same
            if os.path.exists(dest_acl_file) and os.path.samefile(acl_file, dest_acl_file):
                logger.info("Skipping acl.json that would copy to itself", extra={"acl_file": acl_file})
            else:
                logger.info("Moving acl.json to metadata directory", extra={"acl_file": acl_file})
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
                    logger.info("Skipping acl.json that would copy to itself", extra={"acl_file": acl_file})
                else:
                    logger.info("Found acl.json, moving to metadata directory", extra={"acl_file": acl_file})
                    shutil.copy2(acl_file, dest_acl_file)
                return
                
        logger.warning("acl.json not found in source directory")
    
    def _find_data_directory(self, source_dir: str) -> Optional[str]:
        """Find the data directory in the source directory"""
        direct = os.path.join(source_dir, OCFL_DATA_DIR)
        if os.path.isdir(direct):
            return direct

        for root, dirs, _ in os.walk(source_dir):
            if OCFL_DATA_DIR in dirs:
                return os.path.join(root, OCFL_DATA_DIR)

        return None
    
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """
        Move a folder from ingest to production, ensuring OCFL structure.
        
        Args:
            source_prefix (str): The path in the ingest bucket to move
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        logger.info("Starting move to production", extra={"source_prefix": source_prefix})
        
        try:
            # First validate the structure
            validation_result = self.validate_structure(source_prefix)
            
            if not validation_result["success"]:
                if validation_result.get("needs_transform", False):
                    # Structure needs transformation
                    logger.info("Structure needs transformation", extra={"source_prefix": source_prefix})
                    return self.transform_structure(source_prefix)
                else:
                    logger.error("Validation failed", extra={"error": validation_result.get('error', 'Unknown error')})
                    return validation_result
            
            # Structure is valid, copy directly
            try:
                logger.info("Structure is valid, copying directly to production", extra={"source_prefix": source_prefix})
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
                
                logger.info("Successfully copied files to production bucket", extra={"copied_files": copied_files, "source_prefix": source_prefix})
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to production bucket ({copied_files} files copied)"
                }
                
            except Exception as copy_error:
                logger.error("Error copying to production", extra={"error": str(copy_error)})
                # If direct copy failed, try transformation as a fallback
                logger.info("Direct copy failed, trying transformation as fallback")
                return self.transform_structure(source_prefix)
                
        except Exception as e:
            logger.error("Error in move_to_production", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }

    def convert_bundle_to_ocfl(self, bucket_name: str, bundle_path: str) -> Dict[str, Any]:
        """
        Convert a bundle to OCFL within the same bucket using atomic operations.

        Args:
            bucket_name (str): Name of bucket containing the bundle
            bundle_path (str): Path to the bundle to convert

        Returns:
            Dict[str, Any]: Result of the conversion
        """
        logger.info("Starting in-place OCFL conversion for bundle", extra={"bundle_path": bundle_path, "bucket_name": bucket_name})

        try:
            # First, analyze the existing structure
            analysis_result = self.analyze_folder_structure(bucket_name, bundle_path)

            if not analysis_result["success"]:
                return analysis_result

            # Check if already OCFL compliant
            if analysis_result["structure_analysis"]["is_ocfl_compliant"]:
                return {
                    "success": True,
                    "message": "Bundle is already OCFL compliant",
                    "needs_conversion": False
                }

            # Create conversion plan
            conversion_plan = self.create_conversion_plan(analysis_result)

            if not conversion_plan["feasible"]:
                return {
                    "success": False,
                    "error": "Conversion not feasible",
                    "details": conversion_plan
                }

            # Perform atomic conversion
            return self._perform_atomic_conversion(bucket_name, bundle_path, conversion_plan)

        except Exception as e:
            logger.error("Error in in-place conversion", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }

    def analyze_folder_structure(self, bucket_name: str, folder_path: str) -> Dict[str, Any]:
        """
        Analyze existing folder for OCFL compatibility and metadata.

        Args:
            bucket_name (str): Name of bucket containing folder
            folder_path (str): Path to folder to analyze

        Returns:
            Dict[str, Any]: Analysis result with structure details
        """
        logger.info("Analyzing folder structure", extra={"folder_path": folder_path})

        try:
            # Get folder contents
            contents = self.bucket_service.list_bucket_contents(bucket_name, folder_path)

            if not contents:
                return {
                    "success": False,
                    "error": f"Folder {folder_path} not found or empty"
                }

            # Analyze structure components
            structure_analysis = {
                "has_ocfl_marker": False,
                "has_version_directory": False,
                "has_content_directory": False,
                "has_metadata_files": False,
                "has_data_directory": False,
                "has_acl_file": False,
                "xml_files": [],
                "total_files": 0,
                "total_size": 0,
                "is_ocfl_compliant": False,
                "partial_ocfl": False
            }

            object_prefix = folder_path if folder_path.endswith('/') else f"{folder_path}/"
            object_keys = self._list_s3_objects(bucket_name, object_prefix)

            # Analyze each item
            for item in contents:
                name = item["name"]

                if name.startswith("0=ocfl_object_"):
                    structure_analysis["has_ocfl_marker"] = True

                if item.get("is_dir", False):
                    # Check for OCFL directories
                    if name == "v1":
                        structure_analysis["has_version_directory"] = True
                    elif name == "content":
                        structure_analysis["has_content_directory"] = True
                    elif name == OCFL_DATA_DIR:
                        structure_analysis["has_data_directory"] = True
                else:
                    # Analyze files
                    filename = name
                    structure_analysis["total_files"] += 1
                    structure_analysis["total_size"] += item.get("size", 0)

                    if filename == "acl.json":
                        structure_analysis["has_acl_file"] = True
                    elif filename.endswith(".xml"):
                        structure_analysis["xml_files"].append(filename)
                        structure_analysis["has_metadata_files"] = True

            # Include nested objects in analysis
            for key in object_keys:
                relative = key[len(object_prefix):]
                if not relative:
                    continue
                if '/' not in relative:
                    continue  # already handled
                if relative.endswith('/'):
                    continue  # skip directory markers

                structure_analysis["total_files"] += 1
                if relative.endswith('.xml'):
                    structure_analysis["has_metadata_files"] = True
                    structure_analysis["xml_files"].append(relative.split('/')[-1])
                if relative.endswith('acl.json'):
                    structure_analysis["has_acl_file"] = True
                if f'/{OCFL_DATA_DIR}/' in relative:
                    structure_analysis["has_data_directory"] = True

            # Determine OCFL compliance
            structure_analysis["is_ocfl_compliant"] = (
                structure_analysis["has_ocfl_marker"] and
                structure_analysis["has_version_directory"] and
                structure_analysis["has_content_directory"]
            )

            structure_analysis["partial_ocfl"] = (
                structure_analysis["has_ocfl_marker"] or
                structure_analysis["has_version_directory"]
            )

            return {
                "success": True,
                "folder_path": folder_path,
                "structure_analysis": structure_analysis,
                "contents": contents
            }

        except Exception as e:
            logger.error("Error analyzing folder structure", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }

    def create_conversion_plan(self, analysis_result: Dict) -> Dict[str, Any]:
        """
        Generate conversion plan based on analysis.

        Args:
            analysis_result (Dict): Result from analyze_folder_structure

        Returns:
            Dict[str, Any]: Conversion plan with steps and feasibility
        """
        structure = analysis_result["structure_analysis"]

        is_ocfl_compliant = structure.get("is_ocfl_compliant", False)
        partial_ocfl = structure.get("partial_ocfl", False)
        has_metadata = structure.get("has_metadata_files", False)
        has_data = structure.get("has_data_directory", False)
        has_acl = structure.get("has_acl_file", False)
        xml_files = structure.get("xml_files", []) or []
        total_files = structure.get("total_files", 0) or 0
        total_size = structure.get("total_size", 0) or 0

        plan = {
            "feasible": True,
            "conversion_type": "unknown",
            "steps": [],
            "preserve_items": [],
            "risks": [],
            "estimated_time": "2-5 minutes"
        }

        try:
            # Determine conversion type
            if is_ocfl_compliant:
                plan["conversion_type"] = "none_needed"
                plan["feasible"] = False
                plan["risks"].append("Already OCFL compliant")
                return plan
            elif partial_ocfl:
                plan["conversion_type"] = "complete_partial"
                plan["steps"] = ["Complete existing OCFL structure", "Reorganize content"]
            elif has_metadata and has_data:
                plan["conversion_type"] = "structured_to_ocfl"
                plan["steps"] = [
                    "Create OCFL markers",
                    "Create v1/content structure",
                    "Move metadata",
                    "Move data files"
                ]
            elif has_metadata or has_data:
                plan["conversion_type"] = "flat_to_ocfl"
                plan["steps"] = ["Create OCFL structure", "Organize files into content/metadata"]
            elif total_files > 0:
                plan["conversion_type"] = "flat_to_ocfl"
                plan["steps"] = ["Create OCFL structure", f"Organize files into content/{OCFL_DATA_DIR}"]
            else:
                plan["conversion_type"] = "unknown_structure"
                plan["feasible"] = False
                plan["risks"].append("Unknown structure type")
                return plan

            # Identify items to preserve
            if has_acl:
                plan["preserve_items"].append("acl.json")

            if xml_files:
                plan["preserve_items"].extend(xml_files)

            # Assess risks
            if total_files > 1000:
                plan["risks"].append("Large number of files may increase processing time")
                plan["estimated_time"] = "10-20 minutes"

            if total_size > 1024 * 1024 * 1024:  # 1GB
                plan["risks"].append("Large folder size may require extended processing time")
                plan["estimated_time"] = "15-30 minutes"

        except Exception as e:
            logger.error("Error creating conversion plan", extra={"error": str(e)})
            plan["feasible"] = False
            plan["risks"].append(f"Planning error: {str(e)}")

        return plan

    def _perform_atomic_conversion(self, bucket_name: str, folder_path: str,
                                  conversion_plan: Dict) -> Dict[str, Any]:
        """
        Perform atomic OCFL conversion using temporary workspace.

        Args:
            bucket_name (str): Name of bucket
            folder_path (str): Path to folder to convert
            conversion_plan (Dict): Conversion plan from create_conversion_plan

        Returns:
            Dict[str, Any]: Conversion result
        """
        logger.info("Performing atomic conversion", extra={"folder_path": folder_path})

        try:
            if conversion_plan.get("conversion_type") in {"structured_to_ocfl", "flat_to_ocfl"}:
                server_result = self._perform_server_side_conversion(bucket_name, folder_path, conversion_plan)
                if server_result.get("success"):
                    return server_result
                if server_result.get("server_side"):
                    logger.warning(
                        "Server-side conversion attempt failed for %s: %s.",
                        folder_path,
                        server_result.get("error"),
                    )
                    return server_result

            return {
                "success": False,
                "error": "Conversion path not supported for in-place server operations",
            }

        except Exception as e:
            logger.error("Error in atomic conversion", extra={"error": str(e)})

            return {
                "success": False,
                "error": f"Atomic conversion failed: {str(e)}",
                "rollback_attempted": True
            }

    def _perform_server_side_conversion(self, bucket_name: str, folder_path: str,
                                        conversion_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt OCFL conversion using in-bucket copy operations."""

        source_prefix = folder_path if folder_path.endswith('/') else f"{folder_path}/"
        temp_prefix = f"{folder_path.rstrip('/')}_ocfl_{uuid.uuid4().hex[:8]}/"

        logger.info("Performing server-side conversion", extra={"folder_path": folder_path, "temp_prefix": temp_prefix})

        metadata_seen: set[str] = set()
        metadata_files: List[str] = []
        files_processed = 0
        manifest_entries: Dict[str, List[str]] = defaultdict(list)
        state_entries: Dict[str, List[str]] = defaultdict(list)

        try:
            # Seed OCFL markers
            self._put_empty_object(bucket_name, f"{temp_prefix}0=ocfl_object_1.0")
            self._put_empty_object(bucket_name, f"{temp_prefix}v1/")
            self._put_empty_object(bucket_name, f"{temp_prefix}v1/content/")
            self._put_empty_object(bucket_name, f"{temp_prefix}v1/content/metadata/")
            self._put_empty_object(bucket_name, f"{temp_prefix}v1/content/{OCFL_DATA_DIR}/")

            for key in self._list_s3_objects(bucket_name, source_prefix):
                if key == source_prefix:
                    continue

                relative_path = key[len(source_prefix):]
                if not relative_path:
                    continue

                lower_rel = relative_path.lower()

                # Skip existing OCFL markers or structures; not supported in server-side flow
                if lower_rel.startswith('0=ocfl_object') or lower_rel.startswith('v1/'):
                    raise ValueError('Existing OCFL structure detected; cannot perform server-side conversion.')

                if lower_rel.endswith('/'):
                    continue

                if lower_rel.endswith('.xml'):
                    dest_rel = self._build_metadata_destination(relative_path, metadata_seen)
                    metadata_files.append(os.path.basename(dest_rel))
                elif lower_rel.endswith('acl.json'):
                    dest_rel = self._build_metadata_destination(relative_path, metadata_seen, force_name='acl.json')
                else:
                    parts = [part for part in relative_path.split('/') if part]
                    if parts and parts[0].lower() == OCFL_DATA_DIR.lower():
                        parts = parts[1:]

                    resource_rel = '/'.join(parts) if parts else os.path.basename(relative_path)
                    dest_rel = f"v1/content/{OCFL_DATA_DIR}/{resource_rel}" if resource_rel else f"v1/content/{OCFL_DATA_DIR}"

                dest_key = f"{temp_prefix}{dest_rel}".replace('//', '/')

                digest = self._compute_sha512_from_s3(bucket_name, key)
                manifest_entries[digest].append(dest_rel)

                logical_path = dest_rel.split('v1/content/', 1)[-1] if dest_rel.startswith('v1/content/') else dest_rel
                state_entries[digest].append(logical_path)

                self.bucket_service.s3_client.copy_object(
                    CopySource={'Bucket': bucket_name, 'Key': key},
                    Bucket=bucket_name,
                    Key=dest_key
                )

                files_processed += 1

            inventory = self._build_inventory(folder_path, manifest_entries, state_entries)
            self._write_inventory_to_s3(bucket_name, temp_prefix, inventory)

            # Replace original prefix with the new OCFL structure
            self._delete_folder_contents(bucket_name, source_prefix)
            self._move_folder_contents(bucket_name, temp_prefix, source_prefix, delete_source=True)
            self._write_inventory_to_s3(bucket_name, source_prefix, inventory)

            return {
                'success': True,
                'message': f'Server-side conversion completed for {folder_path}',
                'conversion_type': conversion_plan.get('conversion_type'),
                'files_processed': files_processed,
                'preserved_items': conversion_plan.get('preserve_items', []),
                'metadata_files': metadata_files,
                'server_side': True,
            }

        except Exception as exc:
            logger.error("Server-side OCFL conversion failed", extra={"error": str(exc)})
            try:
                self._delete_folder_contents(bucket_name, temp_prefix)
            except Exception:
                pass
            return {
                'success': False,
                'error': str(exc),
                'server_side': True,
            }

    def _create_ocfl_structure(self, source_dir: str, target_dir: str,
                              conversion_plan: Dict, object_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create OCFL structure from source directory.

        Args:
            source_dir (str): Path to source directory
            target_dir (str): Path to target OCFL directory
            conversion_plan (Dict): Conversion plan

        Returns:
            Dict[str, Any]: Creation result
        """
        try:
            os.makedirs(target_dir, exist_ok=True)

            # Create OCFL version marker
            version_marker = "0=ocfl_object_1.0"
            with open(os.path.join(target_dir, version_marker), "w") as f:
                f.write("")

            # Create v1/content structure
            v1_dir = os.path.join(target_dir, "v1")
            content_dir = os.path.join(v1_dir, "content")
            metadata_dir = os.path.join(content_dir, "metadata")
            os.makedirs(metadata_dir, exist_ok=True)

            files_processed = 0

            # Process files based on conversion plan
            if conversion_plan["conversion_type"] in ["structured_to_ocfl", "complete_partial"]:
                # Move XML files to metadata
                xml_files = self._find_and_move_xml_files(source_dir, metadata_dir)
                files_processed += len(xml_files)

                # Move ACL file if exists
                if self._move_acl_file_if_exists(source_dir, metadata_dir):
                    files_processed += 1

                # Move data directory if exists
                resources_moved = self._move_data_directory(source_dir, content_dir)
                if resources_moved:
                    files_processed += resources_moved

            elif conversion_plan["conversion_type"] == "flat_to_ocfl":
                # Organize flat structure
                files_processed = self._organize_flat_structure(source_dir, content_dir, metadata_dir)

            inventory = self._build_inventory_from_local(
                target_dir,
                folder_path=(object_id or os.path.basename(source_dir.rstrip('/')) or "object")
            )
            self._write_inventory_to_local(target_dir, inventory)

            return {
                "success": True,
                "files_processed": files_processed,
                "structure_created": "OCFL v1.0"
            }

        except Exception as e:
            logger.error("Error creating OCFL structure", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }

    def _find_and_move_xml_files(self, source_dir: str, metadata_dir: str) -> List[str]:
        """Find and move XML files to metadata directory"""
        xml_files = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                if file.endswith(".xml"):
                    src = os.path.join(root, file)
                    dst = os.path.join(metadata_dir, file)
                    shutil.copy2(src, dst)
                    xml_files.append(file)
                    logger.debug("Moved XML file", extra={"file": file})
        return xml_files

    def _move_acl_file_if_exists(self, source_dir: str, metadata_dir: str) -> bool:
        """Move ACL file if it exists"""
        acl_file = os.path.join(source_dir, "acl.json")
        if os.path.exists(acl_file):
            dst = os.path.join(metadata_dir, "acl.json")
            shutil.copy2(acl_file, dst)
            logger.debug("Moved acl.json file")
            return True
        return False

    def _move_data_directory(self, source_dir: str, content_dir: str) -> int:
        """Move data directory if it exists"""
        data_dir = os.path.join(source_dir, OCFL_DATA_DIR)
        if os.path.isdir(data_dir):
            dst = os.path.join(content_dir, OCFL_DATA_DIR)
            shutil.copytree(data_dir, dst, dirs_exist_ok=True)
            file_count = sum(len(files) for _, _, files in os.walk(dst))
            logger.debug("Moved data directory", extra={"file_count": file_count})
            return file_count
        return 0

    def _organize_flat_structure(self, source_dir: str, content_dir: str, metadata_dir: str) -> int:
        """Organize flat file structure into OCFL format"""
        files_processed = 0

        for root, _, files in os.walk(source_dir):
            for file in files:
                src = os.path.join(root, file)
                rel_path = os.path.relpath(src, source_dir)

                if file.endswith(".xml") or file == "acl.json":
                    # Move to metadata
                    dst = os.path.join(metadata_dir, os.path.basename(rel_path))
                    shutil.copy2(src, dst)
                else:
                    # Move to data directory
                    data_dir = os.path.join(content_dir, OCFL_DATA_DIR)
                    os.makedirs(data_dir, exist_ok=True)
                    dst = os.path.join(data_dir, rel_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

                files_processed += 1

        return files_processed

    def _list_s3_objects(self, bucket_name: str, prefix: str) -> List[str]:
        paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")
        queue = [prefix]
        keys: List[str] = []
        processed: set[str] = set()

        while queue:
            current_prefix = queue.pop(0)
            if current_prefix in processed:
                continue

            processed.add(current_prefix)

            for page in paginator.paginate(Bucket=bucket_name, Prefix=current_prefix, Delimiter='/'):
                keys.extend(obj["Key"] for obj in page.get("Contents", []) if obj.get("Key"))
                for common_prefix in page.get("CommonPrefixes", []):
                    next_prefix = common_prefix.get('Prefix')
                    if next_prefix and next_prefix not in processed:
                        queue.append(next_prefix)

        return keys

    def _put_empty_object(self, bucket_name: str, key: str) -> None:
        self.bucket_service.s3_client.put_object(Bucket=bucket_name, Key=key, Body=b"")

    def _compute_sha512_from_s3(self, bucket_name: str, key: str) -> str:
        hasher = hashlib.sha512()
        response = self.bucket_service.s3_client.get_object(Bucket=bucket_name, Key=key)
        body = response.get('Body')
        if body is None:
            raise ValueError(f"Unable to read object body for {key}")

        chunk = body.read(8192)
        while chunk:
            hasher.update(chunk)
            chunk = body.read(8192)

        if hasattr(body, 'close'):
            body.close()

        return hasher.hexdigest()

    def _build_metadata_destination(self, relative_path: str, existing: set[str], force_name: Optional[str] = None) -> str:
        filename = force_name or os.path.basename(relative_path) or "metadata.xml"
        name, ext = os.path.splitext(filename)
        candidate = f"v1/content/metadata/{filename}"
        counter = 1
        while candidate in existing:
            candidate = f"v1/content/metadata/{name}_{counter}{ext}"
            counter += 1
        existing.add(candidate)
        return candidate

    def _delete_folder_contents(self, bucket_name: str, folder_path: str) -> None:
        """Delete all contents of a folder in S3"""
        try:
            paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name, Prefix=folder_path):
                if "Contents" in page:
                    delete_keys = [{"Key": obj["Key"]} for obj in page["Contents"]]

                    if delete_keys:
                        try:
                            self.bucket_service.s3_client.delete_objects(
                                Bucket=bucket_name,
                                Delete={"Objects": delete_keys}
                            )
                        except ClientError as err:
                            error_code = err.response.get("Error", {}).get("Code")
                            if error_code == "MissingContentMD5":
                                for key_info in delete_keys:
                                    self.bucket_service.s3_client.delete_object(
                                        Bucket=bucket_name,
                                        Key=key_info["Key"]
                                    )
                            else:
                                raise

        except Exception as e:
            logger.error("Error deleting folder contents", extra={"error": str(e)})
            raise

    def _move_folder_contents(self, bucket_name: str, source_path: str, target_path: str, delete_source: bool = False) -> None:
        """Move contents from source folder to target folder in S3.

        Args:
            bucket_name: Name of the bucket containing the objects.
            source_path: Source prefix to move (with or without trailing slash).
            target_path: Destination prefix.
            delete_source: When True, delete each source object after copying (behaves like rename).
        """
        try:
            paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")

            source_prefix = source_path if source_path.endswith('/') else f"{source_path}/"
            target_prefix = target_path if target_path.endswith('/') else f"{target_path}/"

            for page in paginator.paginate(Bucket=bucket_name, Prefix=source_prefix):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        source_key = obj["Key"]

                        if source_key == source_prefix:
                            continue

                        relative_path = source_key[len(source_prefix):]
                        target_key = f"{target_prefix}{relative_path}" if relative_path else target_prefix.rstrip('/')

                        # Copy object to new location
                        self.bucket_service.s3_client.copy_object(
                            CopySource={"Bucket": bucket_name, "Key": source_key},
                            Bucket=bucket_name,
                            Key=target_key
                        )

                        if delete_source:
                            self.bucket_service.s3_client.delete_object(
                                Bucket=bucket_name,
                                Key=source_key
                            )

        except Exception as e:
            logger.error("Error moving folder contents", extra={"error": str(e)})
            raise 

    def _build_inventory(self, folder_path: str, manifest_entries: Dict[str, List[str]],
                         state_entries: Dict[str, List[str]]) -> Dict[str, Any]:
        manifest = {digest: sorted(paths) for digest, paths in manifest_entries.items()}
        state = {digest: sorted(paths) for digest, paths in state_entries.items()}

        inventory = {
            "id": folder_path.rstrip('/'),
            "type": "https://ocfl.io/1.1/spec/#inventory",
            "digestAlgorithm": "sha512",
            "head": "v1",
            "contentDirectory": "content",
            "manifest": manifest,
            "versions": {
                "v1": {
                    "created": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                    "state": state
                }
            }
        }

        return inventory

    def _serialize_inventory(self, inventory: Dict[str, Any]) -> bytes:
        return json.dumps(inventory, indent=2, sort_keys=True).encode('utf-8') + b"\n"

    def _write_inventory_to_s3(self, bucket_name: str, temp_prefix: str, inventory: Dict[str, Any]) -> None:
        prefix = temp_prefix if temp_prefix.endswith('/') else f"{temp_prefix}/"
        inventory_bytes = self._serialize_inventory(inventory)
        inventory_digest = hashlib.sha512(inventory_bytes).hexdigest()
        digest_body = f"{inventory_digest} inventory.json\n".encode('utf-8')

        targets = [
            f"{prefix}inventory.json",
            f"{prefix}inventory.json.sha512",
            f"{prefix}v1/inventory.json",
            f"{prefix}v1/inventory.json.sha512",
        ]
        bodies = [inventory_bytes, digest_body, inventory_bytes, digest_body]

        for key, body in zip(targets, bodies):
            self.bucket_service.s3_client.put_object(Bucket=bucket_name, Key=key, Body=body)

    def _build_inventory_from_local(self, target_dir: str, folder_path: str) -> Dict[str, Any]:
        content_root = os.path.join(target_dir, "v1", "content")
        manifest_entries: Dict[str, List[str]] = defaultdict(list)
        state_entries: Dict[str, List[str]] = defaultdict(list)

        for root, _, files in os.walk(content_root):
            for file in files:
                file_path = os.path.join(root, file)
                digest = self._compute_sha512_from_file(file_path)

                rel_from_v1 = os.path.relpath(file_path, os.path.join(target_dir, "v1"))
                rel_from_v1 = rel_from_v1.replace(os.sep, '/')
                manifest_entries[digest].append(f"v1/{rel_from_v1}")

                logical_path = os.path.relpath(file_path, content_root).replace(os.sep, '/')
                state_entries[digest].append(logical_path)

        return self._build_inventory(folder_path, manifest_entries, state_entries)

    def _compute_sha512_from_file(self, file_path: str) -> str:
        hasher = hashlib.sha512()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    def _write_inventory_to_local(self, target_dir: str, inventory: Dict[str, Any]) -> None:
        inventory_bytes = self._serialize_inventory(inventory)
        inventory_digest = hashlib.sha512(inventory_bytes).hexdigest()
        digest_body = f"{inventory_digest} inventory.json\n".encode('utf-8')

        root_inventory = os.path.join(target_dir, "inventory.json")
        with open(root_inventory, 'wb') as f:
            f.write(inventory_bytes)

        with open(f"{root_inventory}.sha512", 'wb') as f:
            f.write(digest_body)

        v1_dir = os.path.join(target_dir, "v1")
        os.makedirs(v1_dir, exist_ok=True)

        with open(os.path.join(v1_dir, "inventory.json"), 'wb') as f:
            f.write(inventory_bytes)

        with open(os.path.join(v1_dir, "inventory.json.sha512"), 'wb') as f:
            f.write(digest_body)
