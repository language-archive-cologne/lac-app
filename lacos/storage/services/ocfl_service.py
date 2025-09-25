import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid

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

    def convert_bundle_to_ocfl(self, bucket_name: str, bundle_path: str) -> Dict[str, Any]:
        """
        Convert a bundle to OCFL within the same bucket using atomic operations.

        Args:
            bucket_name (str): Name of bucket containing the bundle
            bundle_path (str): Path to the bundle to convert

        Returns:
            Dict[str, Any]: Result of the conversion
        """
        logger.info(f"Starting in-place OCFL conversion for bundle {bundle_path} in {bucket_name}")

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
            logger.error(f"Error in in-place conversion: {str(e)}")
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
        logger.info(f"Analyzing folder structure: {folder_path}")

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
                "has_resources_directory": False,
                "has_acl_file": False,
                "xml_files": [],
                "total_files": 0,
                "total_size": 0,
                "is_ocfl_compliant": False,
                "partial_ocfl": False
            }

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
                    elif name == "Resources":
                        structure_analysis["has_resources_directory"] = True
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
            logger.error(f"Error analyzing folder structure: {str(e)}")
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
        has_resources = structure.get("has_resources_directory", False)
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
            elif has_metadata and has_resources:
                plan["conversion_type"] = "structured_to_ocfl"
                plan["steps"] = ["Create OCFL markers", "Create v1/content structure", "Move metadata", "Move resources"]
            elif has_metadata or has_resources:
                plan["conversion_type"] = "flat_to_ocfl"
                plan["steps"] = ["Create OCFL structure", "Organize files into content/metadata"]
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
            logger.error(f"Error creating conversion plan: {str(e)}")
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
        logger.info(f"Performing atomic conversion for {folder_path}")

        temp_workspace = None
        temp_suffix = str(uuid.uuid4())[:8]
        temp_folder_path = f"{folder_path}_temp_{temp_suffix}"

        try:
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_workspace:
                logger.debug(f"Using temporary workspace: {temp_workspace}")

                # Download original folder to temp workspace
                original_dir = os.path.join(temp_workspace, "original")
                self.bucket_service._download_directory(bucket_name, folder_path, original_dir)

                # Create OCFL structure in temp workspace
                ocfl_dir = os.path.join(temp_workspace, "ocfl_converted")
                conversion_result = self._create_ocfl_structure(
                    original_dir, ocfl_dir, conversion_plan
                )

                if not conversion_result["success"]:
                    return conversion_result

                # Upload converted structure to temporary location in bucket
                upload_result = self.bucket_service._upload_directory(
                    ocfl_dir, bucket_name, temp_folder_path
                )

                if not upload_result["success"]:
                    return {
                        "success": False,
                        "error": "Failed to upload converted structure",
                        "details": upload_result
                    }

                # Atomic replacement: delete original and rename temp
                try:
                    # Delete original folder
                    self._delete_folder_contents(bucket_name, folder_path)

                    # Move temp folder to original location
                    self._move_folder_contents(bucket_name, temp_folder_path, folder_path)

                    # Clean up temp folder
                    self._delete_folder_contents(bucket_name, temp_folder_path)

                    logger.info(f"Successfully completed atomic conversion of {folder_path}")

                    return {
                        "success": True,
                        "message": f"Successfully converted {folder_path} to OCFL format",
                        "conversion_type": conversion_plan["conversion_type"],
                        "files_processed": conversion_result.get("files_processed", 0),
                        "preserved_items": conversion_plan["preserve_items"]
                    }

                except Exception as atomic_error:
                    # Attempt to rollback by cleaning up temp folder
                    try:
                        self._delete_folder_contents(bucket_name, temp_folder_path)
                    except:
                        pass

                    raise atomic_error

        except Exception as e:
            logger.error(f"Error in atomic conversion: {str(e)}")

            # Clean up temp folder if it exists
            try:
                self._delete_folder_contents(bucket_name, temp_folder_path)
            except:
                pass

            return {
                "success": False,
                "error": f"Atomic conversion failed: {str(e)}",
                "rollback_attempted": True
            }

    def _create_ocfl_structure(self, source_dir: str, target_dir: str,
                              conversion_plan: Dict) -> Dict[str, Any]:
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

                # Move Resources directory if exists
                resources_moved = self._move_resources_directory(source_dir, content_dir)
                if resources_moved:
                    files_processed += resources_moved

            elif conversion_plan["conversion_type"] == "flat_to_ocfl":
                # Organize flat structure
                files_processed = self._organize_flat_structure(source_dir, content_dir, metadata_dir)

            return {
                "success": True,
                "files_processed": files_processed,
                "structure_created": "OCFL v1.0"
            }

        except Exception as e:
            logger.error(f"Error creating OCFL structure: {str(e)}")
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
                    logger.debug(f"Moved XML file: {file}")
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

    def _move_resources_directory(self, source_dir: str, content_dir: str) -> int:
        """Move Resources directory if it exists"""
        resources_dir = os.path.join(source_dir, "Resources")
        if os.path.isdir(resources_dir):
            dst_resources = os.path.join(content_dir, "Resources")
            shutil.copytree(resources_dir, dst_resources)
            # Count files in Resources directory
            file_count = sum(len(files) for _, _, files in os.walk(dst_resources))
            logger.debug(f"Moved Resources directory with {file_count} files")
            return file_count
        return 0

    def _organize_flat_structure(self, source_dir: str, content_dir: str, metadata_dir: str) -> int:
        """Organize flat file structure into OCFL format"""
        files_processed = 0

        for root, dirs, files in os.walk(source_dir):
            for file in files:
                src = os.path.join(root, file)

                if file.endswith(".xml") or file == "acl.json":
                    # Move to metadata
                    dst = os.path.join(metadata_dir, file)
                    shutil.copy2(src, dst)
                else:
                    # Move to Resources
                    resources_dir = os.path.join(content_dir, "Resources")
                    os.makedirs(resources_dir, exist_ok=True)
                    dst = os.path.join(resources_dir, file)
                    shutil.copy2(src, dst)

                files_processed += 1

        return files_processed

    def _delete_folder_contents(self, bucket_name: str, folder_path: str) -> None:
        """Delete all contents of a folder in S3"""
        try:
            paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name, Prefix=folder_path):
                if "Contents" in page:
                    delete_keys = [{"Key": obj["Key"]} for obj in page["Contents"]]

                    if delete_keys:
                        self.bucket_service.s3_client.delete_objects(
                            Bucket=bucket_name,
                            Delete={"Objects": delete_keys}
                        )

        except Exception as e:
            logger.error(f"Error deleting folder contents: {str(e)}")
            raise

    def _move_folder_contents(self, bucket_name: str, source_path: str, target_path: str) -> None:
        """Move contents from source folder to target folder in S3"""
        try:
            paginator = self.bucket_service.s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name, Prefix=source_path):
                if "Contents" in page:
                    for obj in page["Contents"]:
                        source_key = obj["Key"]
                        # Calculate target key by replacing prefix
                        relative_path = source_key[len(source_path):].lstrip("/")
                        target_key = f"{target_path.rstrip('/')}/{relative_path}" if relative_path else target_path

                        # Copy object to new location
                        self.bucket_service.s3_client.copy_object(
                            CopySource={"Bucket": bucket_name, "Key": source_key},
                            Bucket=bucket_name,
                            Key=target_key
                        )

        except Exception as e:
            logger.error(f"Error moving folder contents: {str(e)}")
            raise 
