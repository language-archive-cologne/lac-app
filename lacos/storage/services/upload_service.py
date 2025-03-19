import logging
import time
from typing import Dict, Any, List, Tuple, Set

import boto3
# Import TransferConfig directly from boto3.s3.transfer
from boto3.s3.transfer import TransferConfig

from .base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)

class UploadService(BaseStorageService):
    """
    Service for handling file uploads to S3/MinIO buckets.
    
    This simplified service focuses solely on uploading files directly from browser requests.
    """
    
    def __init__(self):
        """Initialize the UploadService with base storage configuration."""
        super().__init__()
        logger.info("UploadService initialized")

    def _configure_transfer(self) -> TransferConfig:
        """
        Configure S3 transfer parameters for multipart uploads.
        
        Returns:
            TransferConfig: Configured transfer settings for S3 uploads
        """
        # Configure multipart upload with optimized settings
        multipart_threshold = 8 * 1024 * 1024  # 8 MB
        max_concurrency = 5
        
        transfer_config = TransferConfig(
            multipart_threshold=multipart_threshold,
            max_concurrency=max_concurrency,
            multipart_chunksize=multipart_threshold,
            use_threads=True
        )
        
        logger.info(f"Transfer configuration: threshold={self._format_size(multipart_threshold)}, "
                  f"max_concurrency={max_concurrency}, chunk_size={self._format_size(multipart_threshold)}")
        
        return transfer_config
    
    def _upload_single_file(self, file, file_name: str, file_size: int, bucket_name: str, 
                          relative_path: str, transfer_config) -> Dict[str, Any]:
        """
        Upload a single file to S3.
        
        Args:
            file: The file object to upload
            file_name: Name of the file
            file_size: Size of the file in bytes
            bucket_name: Name of the S3 bucket
            relative_path: Path where the file will be stored in S3
            transfer_config: S3 transfer configuration
            
        Returns:
            Dict containing upload details or error information
        """
        try:
            logger.info(f"Uploading file: {file_name} → {relative_path}")
            
            # Create a buffered copy of the file content to prevent "seek of closed file" errors
            # when the same file is uploaded to multiple paths
            try:
                # First try to read the content (this may fail if file is already closed)
                file.seek(0)
                content = file.read()
                from io import BytesIO
                file_buffer = BytesIO(content)
            except (ValueError, AttributeError) as e:
                # If the file is already closed or doesn't support seek/read, log it
                logger.warning(f"Could not read file {file_name} - creating empty buffer: {str(e)}")
                # Create an empty file with the same name as a fallback
                from io import BytesIO
                file_buffer = BytesIO(b"")
                
            # Upload the file to the exact path provided using the buffer instead of original file
            self.s3_client.upload_fileobj(
                file_buffer,
                bucket_name,
                relative_path,
                Config=transfer_config
            )
            
            logger.info(f"✅ Successfully uploaded {file_name} to {bucket_name}/{relative_path}")
            
            return {
                "success": True,
                "name": file_name,
                "s3_key": relative_path,
                "size": file_size,
                "size_formatted": self._format_size(file_size)
            }
            
        except Exception as e:
            logger.error(f"❌ Error uploading {file_name}: {str(e)}")
            logger.error("Full stack trace:", exc_info=True)
            
            return {
                "success": False,
                "name": file_name,
                "error": str(e)
            }
    
    def _visualize_structure(self, s3_keys_structure: Dict[str, Dict]) -> None:
        """
        Visualize the structure of files uploaded to S3.
        
        Args:
            s3_keys_structure: Dictionary mapping S3 keys to file info
        """
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
    
    def _log_upload_stats(self, uploaded_files: List[Dict], failed_files: List[Dict], 
                        total_size: int, duration: float) -> None:
        """
        Log statistics about the upload operation.
        
        Args:
            uploaded_files: List of successfully uploaded files
            failed_files: List of files that failed to upload
            total_size: Total size of uploaded files in bytes
            duration: Duration of the upload operation in seconds
        """
        avg_speed = total_size / duration if duration > 0 else 0
        
        logger.info(f"Upload process completed:")
        logger.info(f"- Total files uploaded: {len(uploaded_files)}")
        logger.info(f"- Failed uploads: {len(failed_files)}")
        
        if len(failed_files) > 0:
            logger.warning(f"Failed files (first 5): {[f['name'] for f in failed_files[:5]]}")
        
        logger.info(f"- Total size: {self._format_size(total_size)}")
        logger.info(f"- Duration: {duration:.2f} seconds")
        logger.info(f"- Average speed: {self._format_size(avg_speed)}/s")
        
        return avg_speed
    
    def _process_file_paths(self, file_paths: Dict[str, str]) -> Dict[str, str]:
        """
        Process and organize file paths.
        
        Args:
            file_paths: Dictionary mapping paths to file names or file names to paths
                        (depending on how the data was provided from the frontend)
            
        Returns:
            Dictionary mapping full paths to file names
        """
        # The expected format we need is a dict with paths as keys and filenames as values
        
        # First, detect the input format
        if not file_paths:
            logger.warning("No file paths provided")
            return {}
            
        # Take the first key to determine the format
        first_key = next(iter(file_paths.keys()))
        first_value = file_paths[first_key]
        
        # If the key contains a slash (path-like) and the value doesn't, 
        # we already have the correct format: path -> filename
        if "/" in first_key and "/" not in first_value:
            logger.info("File paths are already in correct format (paths as keys)")
            return file_paths
        
        # If the key doesn't contain a slash but the value does,
        # we need to invert: filename -> path becomes path -> filename
        elif "/" not in first_key and "/" in first_value:
            inverted_paths = {}
            for filename, path in file_paths.items():
                inverted_paths[path] = filename
                
            logger.info(f"Inverted file paths from filename->path to path->filename format")
            return inverted_paths
        
        # If both key and value have slashes or neither do, log a warning and try to infer
        else:
            logger.warning(f"Ambiguous file path format. Keys and values both have or don't have path separators.")
            # Default to using the input as-is with a warning
            return file_paths
    
    def _debug_file_paths(self, file_paths: Dict[str, str]) -> None:
        """
        Log file path information for debugging purposes.
        
        Args:
            file_paths: Dictionary mapping either file names to paths or paths to file names
        """
        logger.info("=" * 50)
        logger.info("DEBUG - RECEIVED FILE PATHS:")
        if file_paths:
            for key, value in file_paths.items():
                if "/" in key:  # path -> filename format
                    logger.info(f"  Path: {key} → File: {value}")
                else:  # filename -> path format
                    logger.info(f"  File: {key} → Path: {value}")
        logger.info("=" * 50)
    
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
        # Set default bucket and validate inputs
        if bucket_name is None:
            bucket_name = self.ingest_bucket
        
        if not files:
            return {"success": False, "error": "No files provided for upload"}
            
        if not folder_name:
            return {"success": False, "error": "No folder name provided for upload"}
            
        file_paths = file_paths or {}
        
        # Log initial information
        logger.info(f"Starting direct upload process for folder '{folder_name}' to bucket '{bucket_name}'")
        logger.info(f"Total number of files to process: {len(files)}")
        
        if file_paths:
            logger.info(f"Path information available for {len(file_paths)} files")
            self._debug_file_paths(file_paths)
        
        # Ensure the bucket exists
        if not self.ensure_bucket_exists(bucket_name):
            return {"success": False, "error": f"Failed to ensure bucket exists: {bucket_name}"}
        
        # Configure multipart upload
        transfer_config = self._configure_transfer()
        
        try:
            uploaded_files = []
            failed_files = []
            total_size = 0
            start_time = time.time()
            
            logger.info(f"Starting upload of {len(files)} files to {bucket_name}")
            
            # Track all used S3 keys to visualize the resulting structure
            s3_keys_structure = {}
            
            # Process paths to handle duplicate filenames by using full paths as keys
            path_to_file = self._process_file_paths(file_paths)
            
            # Create a map of files by name for easy access
            file_map = {file.name: file for file in files}
            
            # Create a map to track file usage - some files may be used in multiple paths
            # For each filename, this tracks how many paths use it and how many times it's been processed
            file_usage = {}
            for full_path, file_name in path_to_file.items():
                if file_name in file_usage:
                    file_usage[file_name]["total_paths"] += 1
                else:
                    file_usage[file_name] = {
                        "total_paths": 1,
                        "processed_paths": 0
                    }
            
            # Log file usage information for debugging
            for file_name, usage in file_usage.items():
                if usage["total_paths"] > 1:
                    logger.info(f"File {file_name} will be used in {usage['total_paths']} different paths")
            
            # Track which files were successfully processed to avoid duplicate checking
            processed_files = set()
            processed_paths = set()  # Track by path which is more reliable for duplicates
            
            # Process each full path
            missing_files = []
            for full_path, file_name in path_to_file.items():
                # Check if we have the file in our files collection
                if file_name not in file_map:
                    logger.warning(f"Skipping path {full_path}: File {file_name} not found in uploaded files")
                    missing_files.append({
                        "name": file_name,
                        "path": full_path,
                        "error": "File not found in uploaded files"
                    })
                    continue
                
                # If we've already processed this exact path, skip it
                if full_path in processed_paths:
                    logger.warning(f"Skipping duplicate path: {full_path}")
                    continue
                
                # Get the file and its size
                file = file_map[file_name]
                file_size = file.size
                
                # Upload the file using the full path
                result = self._upload_single_file(
                    file, file_name, file_size, bucket_name, full_path, transfer_config
                )
                
                # Track usage for this file
                if file_name in file_usage:
                    file_usage[file_name]["processed_paths"] += 1
                
                if result["success"]:
                    total_size += file_size
                    uploaded_files.append(result)
                    s3_keys_structure[full_path] = {'file': file_name, 'size': file_size}
                else:
                    failed_files.append(result)
                
                # Mark this path as processed regardless of success/failure
                processed_paths.add(full_path)
                
                # Only mark the file as fully processed if we've used it for all its paths
                if file_name in file_usage and file_usage[file_name]["processed_paths"] >= file_usage[file_name]["total_paths"]:
                    processed_files.add(file_name)
                    logger.info(f"File {file_name} has been used in all {file_usage[file_name]['total_paths']} paths")
            
            # Check for files that had no path information
            for file_name, file in file_map.items():
                # Skip files we've already processed
                if file_name in processed_files:
                    continue
                
                # If the file wasn't processed (not in our processed_files set)
                logger.warning(f"Skipping file {file_name}: No path information available")
                failed_files.append({
                    "name": file_name,
                    "error": "Missing path information"
                })
            
            # Add any missing files to the failed files list
            failed_files.extend(missing_files)
            
            # Visualize the resulting structure
            self._visualize_structure(s3_keys_structure)
            
            # Log statistics and calculate results
            end_time = time.time()
            duration = end_time - start_time
            avg_speed = self._log_upload_stats(uploaded_files, failed_files, total_size, duration)
            
            # Return the results
            return {
                "success": len(failed_files) == 0,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "total_files": len(uploaded_files),
                "total_failed": len(failed_files),
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "target_bucket": bucket_name,
                "target_prefix": folder_name + "/",  # Keep this for view compatibility
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