import logging
import os
import tempfile
import time
from typing import Dict, Any, List
import shutil
from pathlib import Path

import boto3

from .base_storage_service import BaseStorageService
from .collection_service import CollectionService

logger = logging.getLogger(__name__)

class UploadService(BaseStorageService):
    """
    Service for handling file and directory uploads to S3/MinIO buckets.
    
    This service extends BaseStorageService to provide specialized functionality
    for uploading files and directories, including support for collections.
    """
    
    def __init__(self):
        """Initialize the UploadService with base storage configuration."""
        super().__init__()
        # Create a collection service instance for collection-specific operations
        self.collection_service = CollectionService()
        # Ensure collection service uses the same configuration
        self.set_client_and_buckets(self.collection_service)
        logger.info("UploadService initialized")
    
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
        except Exception as e:
            logger.error(f"Error downloading directory {prefix}: {str(e)}")
            raise
    
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
            
            # Use the _upload_directory method to handle the upload
            upload_result = self._upload_directory(local_folder_path, bucket_name, full_prefix)
            
            return upload_result
        except Exception as e:
            logger.error(f"Error uploading folder {local_folder_path}: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
            
            # Track all used S3 keys to visualize the resulting structure
            s3_keys_structure = {}
            
            # Initial check if this is likely a collection
            is_collection = self.collection_service.is_collection_path(target_prefix)
            if is_collection:
                logger.info(f"Detected collection structure in {target_prefix}, using specialized upload logic")
            
            # Track already processed critical files at parent levels to avoid redundant uploads
            processed_parent_critical_files = set()
            
            # Scan directory for critical files first to ensure they're added at all levels
            critical_files = {}
            for root, dirs, files in os.walk(local_dir):
                for file in files:
                    if file.startswith("0=ocfl_object_") or file == "acl.json":
                        local_path = os.path.join(root, file)
                        critical_files[file] = local_path
                        
                        # Also extract the folder structure to identify collection structure
                        rel_path = os.path.relpath(os.path.dirname(local_path), local_dir)
                        path_parts = rel_path.split(os.path.sep)
                        
                        if len(path_parts) >= 1 and path_parts[0]:  # If there's at least one subdirectory
                            # Create parent path key for duplicating at the parent level
                            parent_path = path_parts[0]
                            parent_s3_key = f"{target_prefix}{file}"
                            
                            parent_critical_id = f"{parent_path}:{file}"
                            
                            if parent_critical_id not in processed_parent_critical_files:
                                processed_parent_critical_files.add(parent_critical_id)
                                logger.info(f"Identified critical file {file} for parent-level duplication at {parent_s3_key}")
            
            # Now walk through the directory and upload all files
            for root, dirs, files in os.walk(local_dir):
                for file in files:
                    local_path = os.path.join(root, file)
                    
                    # Calculate the relative path from the local directory
                    rel_path = os.path.relpath(local_path, local_dir)
                    
                    # Create the S3 key (path in the bucket)
                    s3_key = f"{target_prefix.rstrip('/')}/{rel_path}"
                    
                    # Check if this specific path is part of a collection structure
                    # This allows for detecting collections deeper in the structure
                    path_is_collection = is_collection or self.collection_service.is_collection_path(s3_key)
                    
                    try:
                        # Get file size
                        file_size = os.path.getsize(local_path)
                        total_size += file_size
                        
                        # Upload the file using multipart upload instead of upload_file
                        # Configure multipart upload with optimized settings
                        transfer_config = boto3.s3.transfer.TransferConfig(
                            multipart_threshold=8 * 1024 * 1024,  # 8 MB
                            max_concurrency=5,
                            multipart_chunksize=8 * 1024 * 1024,  # 8 MB
                            use_threads=True
                        )
                        
                        # Upload directly using multipart upload
                        with open(local_path, 'rb') as f:
                            self.s3_client.upload_fileobj(
                                f,
                                bucket_name, 
                                s3_key,
                                Config=transfer_config
                            )
                        
                        logger.debug(f"Uploaded {local_path} to {s3_key}")
                        
                        uploaded_files.append({
                            "local_path": local_path,
                            "s3_key": s3_key,
                            "size": file_size,
                            "size_formatted": self._format_size(file_size)
                        })
                        
                        # Handle critical files for collections
                        if path_is_collection and (file.startswith("0=ocfl_object_") or file == "acl.json"):
                            logger.info(f"Found critical file {file} for collection structure at {s3_key}")
                            
                            # Get the parent collection path from the relative path
                            rel_parts = rel_path.split(os.path.sep)
                            if len(rel_parts) >= 1 and rel_parts[0]:  # If there's at least one subdirectory
                                parent_path = rel_parts[0]
                                parent_s3_key = f"{target_prefix.split('/')[0]}/{file}"
                                
                                # Create a unique identifier for this parent critical file
                                parent_critical_id = f"{parent_path}:{file}"
                                
                                # Only upload to parent level if not already processed and the keys are different
                                if parent_s3_key != s3_key:
                                    logger.info(f"Adding critical file {file} at parent level: {parent_s3_key}")
                                    try:
                                        # Configure multipart upload with optimized settings
                                        transfer_config = boto3.s3.transfer.TransferConfig(
                                            multipart_threshold=8 * 1024 * 1024,  # 8 MB
                                            max_concurrency=5,
                                            multipart_chunksize=8 * 1024 * 1024,  # 8 MB
                                            use_threads=True
                                        )
                                        
                                        # Upload directly from the local file using multipart
                                        with open(local_path, 'rb') as f:
                                            self.s3_client.upload_fileobj(
                                                f,
                                                bucket_name,
                                                parent_s3_key,
                                                Config=transfer_config
                                            )
                                        
                                        uploaded_files.append({
                                            "local_path": local_path,
                                            "s3_key": parent_s3_key,
                                            "size": file_size,
                                            "size_formatted": self._format_size(file_size)
                                        })
                                        
                                        # Add to structure visualization
                                        s3_keys_structure[parent_s3_key] = {'file': rel_path, 'size': file_size}
                                        
                                        processed_parent_critical_files.add(parent_critical_id)
                                        logger.info(f"Successfully duplicated {file} to parent level {parent_s3_key}")
                                    except Exception as e:
                                        logger.warning(f"Failed to upload critical file to parent level {parent_s3_key}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error uploading {local_path}: {str(e)}")
                        failed_files.append({
                            "local_path": local_path,
                            "error": str(e)
                        })
            
            # For collections, ensure critical files exist at the top parent level
            if is_collection:
                parent_path = target_prefix.split('/', 1)[0]
                
                # Add any missing critical files to parent level
                for file_name, local_path in critical_files.items():
                    parent_s3_key = f"{parent_path}/{file_name}"
                    parent_critical_id = f"{parent_path}:{file_name}"
                    
                    if parent_critical_id not in processed_parent_critical_files:
                        logger.info(f"Adding critical file {file_name} at top level: {parent_s3_key}")
                        try:
                            # Configure multipart upload with optimized settings
                            transfer_config = boto3.s3.transfer.TransferConfig(
                                multipart_threshold=8 * 1024 * 1024,  # 8 MB
                                max_concurrency=5,
                                multipart_chunksize=8 * 1024 * 1024,  # 8 MB
                                use_threads=True
                            )
                            
                            # Upload directly from the local file using multipart
                            with open(local_path, 'rb') as f:
                                self.s3_client.upload_fileobj(
                                    f,
                                    bucket_name,
                                    parent_s3_key,
                                    Config=transfer_config
                                )
                            
                            uploaded_files.append({
                                "local_path": local_path,
                                "s3_key": parent_s3_key,
                                "size": os.path.getsize(local_path),
                                "size_formatted": self._format_size(os.path.getsize(local_path))
                            })
                            
                            processed_parent_critical_files.add(parent_critical_id)
                        except Exception as e:
                            logger.warning(f"Failed to upload critical file to top level {parent_s3_key}: {str(e)}")
                
                # Create directory markers at all levels
                # Get all parts of the path for nested collections
                parts = target_prefix.rstrip('/').split('/')
                if len(parts) >= 2:
                    # Ensure directory markers exist at each level of the hierarchy
                    for i in range(1, len(parts) + 1):
                        dir_level = '/'.join(parts[:i])
                        dir_marker = f"{dir_level}/"
                        logger.info(f"Ensuring directory marker exists for {dir_marker}")
                        try:
                            self.s3_client.put_object(Bucket=bucket_name, Key=dir_marker, Body="")
                        except Exception as e:
                            logger.warning(f"Could not create directory marker {dir_marker}: {str(e)}")
            
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
    
    def upload_files_directly(self, files, folder_name: str, bucket_name: str = None, file_paths: dict = None) -> Dict[str, Any]:
        """
        Upload files directly from a request to an S3 bucket.
        
        This method is designed to handle uploads from a browser, where the files are
        provided as Django UploadedFile objects, along with a structure of file paths
        typically provided via webkitRelativePath in the browser.
        
        Args:
            files: List of UploadedFile objects, typically from request.FILES
            folder_name (str): The name of the folder to upload to in the bucket
            bucket_name (str, optional): The name of the S3 bucket to upload to. Defaults to ingest bucket.
            file_paths (dict, optional): Dictionary mapping file names to their relative paths
            
        Returns:
            Dict[str, Any]: A dictionary containing the upload results
        """
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        
        # Validate inputs
        if not files:
            return {"success": False, "error": "No files provided for upload"}
            
        if not folder_name:
            return {"success": False, "error": "No folder name provided for upload"}
            
        file_paths = file_paths or {}
        
        logger.info(f"Starting direct upload process for folder '{folder_name}' to bucket '{bucket_name}'")
        logger.info(f"Total number of files to process: {len(files)}")
        
        if file_paths:
            logger.info(f"Path information available for {len(file_paths)} files")
        
        # Debug the file paths to help with debugging
        logger.info("=" * 50)
        logger.info("DEBUG - RECEIVED FILE PATHS:")
        if file_paths:
            for file_name, path in file_paths.items():
                logger.info(f"  File: {file_name} → Path: {path}")
        logger.info("=" * 50)
        
        # Ensure the bucket exists
        if not self.ensure_bucket_exists(bucket_name):
            return {"success": False, "error": f"Failed to ensure bucket exists: {bucket_name}"}
        
        # Configure multipart upload with optimized settings
        multipart_threshold = 8 * 1024 * 1024  # 8 MB
        max_concurrency = 5
        
        transfer_config = boto3.s3.transfer.TransferConfig(
            multipart_threshold=multipart_threshold,
            max_concurrency=max_concurrency,
            multipart_chunksize=multipart_threshold,
            use_threads=True
        )
        
        logger.info(f"Transfer configuration: threshold={self._format_size(multipart_threshold)}, "
                   f"max_concurrency={max_concurrency}, chunk_size={self._format_size(multipart_threshold)}")
        
        try:
            uploaded_files = []
            failed_files = []
            total_size = 0
            start_time = time.time()
            
            prefix = f"{folder_name}/"
            logger.info(f"Starting upload of {len(files)} files to {bucket_name}/{prefix}")
            
            # Track all used S3 keys to visualize the resulting structure
            s3_keys_structure = {}
            
            # Track collections detected in the file structure
            collections = set()
            # Track critical files for later duplication
            critical_files = {}
            # Track already processed critical files at parent levels
            processed_parent_critical_files = set()
            
            # First pass: detect collections by analyzing file paths
            for file in files:
                file_path = file.name
                if not file_path or file_path not in file_paths:
                    continue
                
                relative_path = file_paths[file_path]
                
                # Look for collection paths (where parent/child dirs have the same name)
                # Collection is something like "algerien/algerien"
                path_parts = relative_path.split('/')
                if len(path_parts) >= 2 and self.collection_service.is_collection_path(relative_path):
                    # Get the parent path which should be just the collection name
                    collection_name = path_parts[0]
                    collections.add(collection_name)
                    logger.info(f"Detected collection structure in {relative_path}, parent: {collection_name}")
                
                # Track critical files for collection handling
                if file_path.endswith("0=ocfl_object_1.0") or file_path == "0=ocfl_object_1.0" or file_path.endswith("acl.json") or file_path == "acl.json":
                    critical_files[file_path] = {
                        'file': file,
                        'path': relative_path,
                        's3_key': f"{prefix}{relative_path}"
                    }
                    logger.info(f"Found critical file: {file_path} -> {relative_path}")
            
            # Prepare to track critical files that need to be duplicated at the parent level
            critical_duplications = []

            # Pre-process critical files to prepare parent-level duplications
            for file_path, info in critical_files.items():
                file = info['file']
                relative_path = info['path']
                path_parts = relative_path.split('/')
                
                # Critical files should be duplicated to parent level if they're in a collection-like path
                if len(path_parts) >= 2:
                    # Generate parent level path directly at the collection name level
                    parent_s3_key = f"{folder_name}/{os.path.basename(file_path)}"
                    
                    # Add to the duplication list
                    content = file.read()
                    file.seek(0)  # Reset position for main upload
                    critical_duplications.append({
                        'content': content,
                        'parent_s3_key': parent_s3_key,
                        'file_path': file_path,
                        'file_size': file.size
                    })
            
            # Main upload loop
            for index, file in enumerate(files, 1):
                file_path = file.name
                
                if not file_path:
                    logger.warning(f"Skipping file at index {index}: No file path provided")
                    continue
                
                try:
                    # Use the webkitRelativePath to construct the S3 key
                    # The first part of the path is the root folder name, which we replace with our folder_name
                    relative_path = file_paths[file_path]
                    path_parts = relative_path.split('/')
                    
                    # Log detailed path processing for debugging
                    logger.info(f"[DEBUG] Processing file: {file_path}")
                    logger.info(f"[DEBUG] Relative path: {relative_path}")
                    logger.info(f"[DEBUG] Path parts: {path_parts}")
                    
                    # If there are subdirectories, preserve them in the S3 key
                    if len(path_parts) > 1:
                        # Use the exact relative path with folder_name
                        s3_key = f"{folder_name}/{'/'.join(path_parts[1:])}"
                        logger.info(f"[DEBUG] Using subfolder path: {relative_path}")
                    else:
                        # If it's directly in the root folder, just use the file name
                        s3_key = f"{folder_name}/{file_path}"
                        logger.info(f"[DEBUG] No subfolder, using file name directly")
                    
                    logger.info(f"Using path information for {file_path}: {relative_path} -> {s3_key}")
                    
                    # Track the S3 key in our structure visualization
                    s3_keys_structure[s3_key] = {'file': file_path, 'size': file.size}
                    
                    file_size = file.size
                    total_size += file_size
                    
                    logger.info(f"Processing file {index}/{len(files)}: {file_path}")
                    logger.info(f"File details: size={self._format_size(file_size)}, "
                              f"content_type={file.content_type}, "
                              f"encoding={file.charset if hasattr(file, 'charset') else None}")
                    
                    # Log if using multipart upload
                    if file_size > multipart_threshold:
                        logger.info(f"File {file_path} exceeds multipart threshold "
                                  f"({self._format_size(file_size)} > {self._format_size(multipart_threshold)}), "
                                  "using multipart upload")
                    
                    # Use direct multipart upload without temporary files
                    logger.info(f"Uploading {file_path} using multipart upload directly from memory")
                    file.seek(0)
                    self.s3_client.upload_fileobj(
                        file,
                        bucket_name,
                        s3_key,
                        Config=transfer_config
                    )
                    
                    uploaded_files.append({
                        "name": file_path,
                        "s3_key": s3_key,
                        "size": file_size,
                        "size_formatted": self._format_size(file_size)
                    })
                    
                    logger.info(f"✅ Successfully uploaded {file_path} to {bucket_name}/{s3_key}")
                    
                    # Check if this is a critical file that needs to be duplicated at the parent level
                    is_critical = file_path.endswith("0=ocfl_object_1.0") or file_path == "0=ocfl_object_1.0" or file_path.endswith("acl.json") or file_path == "acl.json"
                    is_collection_path = any(collection_name in s3_key for collection_name in collections)
                    
                    if is_critical and is_collection_path and len(path_parts) >= 2:
                        # Get the parent directory and prepare for parent-level duplication
                        parent_dir = path_parts[0]
                        parent_s3_key = f"{folder_name}/{parent_dir}/{os.path.basename(file_path)}"
                        
                        # Add to the duplication list
                        content = file.read()
                        file.seek(0)  # Reset position for main upload
                        critical_duplications.append({
                            'content': content,
                            'parent_s3_key': parent_s3_key,
                            'file_path': file_path,
                            'file_size': file_size
                        })
                    
                    # Also add collection-level duplication
                    if len(path_parts) >= 2 and file_path.endswith("0=ocfl_object_1.0") or file_path == "0=ocfl_object_1.0" or file_path.endswith("acl.json") or file_path == "acl.json":
                        # Generate collection level path 
                        collection_s3_key = f"{folder_name}/{path_parts[0]}/{os.path.basename(file_path)}"
                        
                        # Only add if it's different from parent_s3_key
                        if collection_s3_key != parent_s3_key:
                            # Save the content for later duplication - convert to bytes if it's not already
                            critical_duplications.append({
                                'content': content,
                                'parent_s3_key': collection_s3_key,
                                'file_path': file_path,
                                'file_size': file.size
                            })
                    
                except Exception as e:
                    logger.error(f"❌ Error uploading {file_path}: {str(e)}")
                    logger.error("Full stack trace:", exc_info=True)
                    failed_files.append({
                        "name": file_path,
                        "error": str(e)
                    })
            
            # Now handle the critical file duplications at parent levels
            logger.info(f"Processing {len(critical_duplications)} critical files for parent-level duplication")
            for duplication in critical_duplications:
                content = duplication['content']
                parent_s3_key = duplication['parent_s3_key']
                file_path = duplication['file_path']
                file_size = duplication['file_size']
                
                logger.info(f"Duplicating critical file {file_path} to parent level: {parent_s3_key}")
                
                try:
                    # Upload directly from content
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=parent_s3_key,
                        Body=content
                    )
                    
                    uploaded_files.append({
                        "name": file_path,
                        "s3_key": parent_s3_key,
                        "size": file_size,
                        "size_formatted": self._format_size(file_size)
                    })
                    
                    # Add to structure visualization
                    s3_keys_structure[parent_s3_key] = {'file': file_path, 'size': file_size}
                    
                    logger.info(f"Successfully duplicated {file_path} to parent level {parent_s3_key}")
                except Exception as e:
                    logger.warning(f"Failed to duplicate critical file to parent level {parent_s3_key}: {str(e)}")
            
            # Log the resulting S3 structure for visualization
            logger.info("=" * 50)
            logger.info("RESULTING S3 STRUCTURE:")
            
            # Group by folder path for visualization
            folder_structure = {}
            for s3_key in s3_keys_structure.keys():
                parts = s3_key.split('/')
                current = folder_structure
                # Build nested structure
                for i, part in enumerate(parts[:-1]):  # Skip the last part (filename)
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                # Add the file at the end
                current[parts[-1]] = "FILE"
            
            # Helper function to print the structure
            def print_structure(structure, indent=0):
                lines = []
                for key, value in structure.items():
                    prefix = "  " * indent
                    if value == "FILE":
                        lines.append(f"{prefix}📄 {key}")
                    else:
                        lines.append(f"{prefix}📁 {key}")
                        child_lines = print_structure(value, indent + 1)
                        lines.extend(child_lines)
                return lines
            
            structure_lines = print_structure(folder_structure)
            for line in structure_lines:
                logger.info(line)
            
            logger.info("=" * 50)
            
            # Calculate and log upload statistics
            end_time = time.time()
            duration = end_time - start_time
            avg_speed = total_size / duration if duration > 0 else 0
            
            logger.info(f"Upload process completed:")
            logger.info(f"- Total files: {len(uploaded_files)}")
            logger.info(f"- Failed files: {len(failed_files)}")
            logger.info(f"- Total size: {self._format_size(total_size)}")
            logger.info(f"- Duration: {duration:.2f} seconds")
            logger.info(f"- Average speed: {self._format_size(avg_speed)}/s")
            
            return {
                "success": len(failed_files) == 0,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "total_failed": len(failed_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "target_prefix": prefix,
                "duration": duration,
                "avg_speed": avg_speed,
                "avg_speed_formatted": self._format_size(avg_speed) + "/s"
            }
        except Exception as e:
            logger.error(f"Error in upload process: {str(e)}")
            logger.error("Full stack trace:", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "uploaded_files": uploaded_files,
                "failed_files": failed_files
            } 