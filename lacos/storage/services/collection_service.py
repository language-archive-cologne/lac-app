import logging
import os
from typing import Dict, Any, List

from .base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)

class CollectionService(BaseStorageService):
    """
    Service for handling collection operations in S3/MinIO buckets.
    
    This service extends BaseStorageService to provide specialized functionality
    for working with collections, which have specific directory structure requirements.
    """
    
    def __init__(self):
        """Initialize the CollectionService with base storage configuration."""
        super().__init__()
        logger.info("CollectionService initialized")
    
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
            # Ensure prefix ends with / if it's not empty to be treated as a directory
            if prefix and not prefix.endswith('/'):
                prefix = prefix + '/'
            
            # List objects directly in the specified prefix using Delimiter
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name, 
                Prefix=prefix,
                Delimiter='/'  # Use delimiter to treat prefix as directory
            )
            
            # Check if any of the objects at this exact level have the OCFL version marker
            for obj in response.get("Contents", []):
                key = obj["Key"]
                filename = os.path.basename(key.rstrip('/'))
                if filename.startswith("0=ocfl_object_"):
                    return True
            
            return False
        except Exception as e:
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
        except Exception as e:
            logger.error(f"Error finding OCFL objects: {str(e)}")
            return []
    
    def is_collection_path(self, path: str) -> bool:
        """
        Determine if a path likely represents a collection (where parent and child directory names are identical).
        
        Args:
            path (str): The path to check
            
        Returns:
            bool: True if it appears to be a collection path, False otherwise
        """
        parts = path.rstrip('/').split('/')
        
        # Check for the simple case: last two parts are identical
        if len(parts) >= 2 and parts[-1] == parts[-2]:
            return True
            
        # Also check for collection paths deeper in the structure
        # For paths like "zaghawa/zaghawa/v1/content" or "test/test/v1/"
        if len(parts) >= 4 and parts[-3] == parts[-4]:
            if parts[-2].startswith('v'):
                return True
        
        # Check paths like "test/test/v1" without trailing slash
        if len(parts) >= 3 and parts[-2] == parts[-3]:
            if parts[-1].startswith('v'):
                return True
                
        return False
    
    def get_collection_parent_path(self, path: str) -> str:
        """
        Extract the parent path for a collection.
        
        Args:
            path (str): The full path to analyze
            
        Returns:
            str: The parent collection path
        """
        parts = path.rstrip('/').split('/')
        
        # Simple case: last two parts are identical (e.g., "zaghawa/zaghawa")
        if len(parts) >= 2 and parts[-1] == parts[-2]:
            return '/'.join(parts[:-1])
            
        # Complex case: deeper structure with v directory (e.g., "zaghawa/zaghawa/v1/content")
        if len(parts) >= 4 and parts[-3] == parts[-4]:
            if parts[-2].startswith('v'):
                return '/'.join(parts[:-3])
                
        # Another case: path with v directory (e.g., "test/test/v1")
        if len(parts) >= 3 and parts[-2] == parts[-3]:
            if parts[-1].startswith('v'):
                return '/'.join(parts[:-2])
                
        # Default case: return the immediate parent
        return '/'.join(parts[:-1])
    
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
            
            # Ensure prefix ends with / if it's not empty to avoid partial matches
            if prefix and not prefix.endswith('/'):
                prefix = prefix + '/'
                logger.info(f"Adjusted prefix to: '{prefix}'")
                
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=prefix, Delimiter="/"
            )
            
            # Log the raw response for debugging
            logger.info(f"DEBUG: S3 list_objects_v2 raw response:")
            if 'Contents' in response:
                logger.info(f"  Contents: {len(response['Contents'])} items")
            else:
                logger.info(f"  Contents: 0 items")
                
            if 'CommonPrefixes' in response:
                logger.info(f"  CommonPrefixes: {len(response['CommonPrefixes'])} items")
                for cp in response.get('CommonPrefixes', []):
                    logger.info(f"    Prefix: {cp.get('Prefix')}")
            else:
                logger.info(f"  CommonPrefixes: 0 items")
            
            contents = []

            for obj in response.get("Contents", []):
                # Skip the directory marker itself if listing a directory
                if prefix and obj["Key"] == prefix:
                    logger.info(f"Skipping directory marker: {obj['Key']}")
                    continue
                    
                item = {
                    "name": os.path.basename(obj["Key"]),
                    "path": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"],
                    "is_dir": False,
                }
                contents.append(item)
                logger.info(f"Found file: {item}")

            for prefix_obj in response.get("CommonPrefixes", []):
                # Extract the folder name from the prefix
                prefix_str = prefix_obj["Prefix"]
                name = os.path.basename(prefix_str.rstrip("/")) 
                
                item = {
                    "name": name,
                    "path": prefix_str,
                    "is_dir": True,
                }
                contents.append(item)
                logger.info(f"Found directory: {item}")

            return contents
        except Exception as e:
            logger.error(
                f"Error listing bucket contents for bucket: '{bucket_name}'. Error: {e}"
            )
            return []
    
    def get_folder_structure(self, bucket_name: str, prefix: str = "") -> Dict[str, Any]:
        """
        Get a hierarchical folder structure starting from the given prefix in the specified bucket.

        Args:
            bucket_name (str): The name of the bucket to get the structure from
            prefix (str, optional): The starting prefix (folder) to build the structure from. Defaults to "".
            
        Returns:
            Dict[str, Any]: Dictionary representing the folder structure with children
        """
        logger.info(f"Getting folder structure for bucket '{bucket_name}' with prefix '{prefix}'")
        
        # First, ensure the bucket exists
        if not self.ensure_bucket_exists(bucket_name):
            logger.warning(f"Cannot get folder structure: Bucket '{bucket_name}' does not exist or is not accessible")
            return {"type": "folder", "name": bucket_name, "path": "", "children": []}
        
        try:
            contents = self.list_bucket_contents(bucket_name, prefix)
            
            # Debug log the contents
            logger.info(f"DEBUG: Bucket contents for '{bucket_name}' with prefix '{prefix}':")
            for item in contents:
                logger.info(f"  {item.get('name')} - type: {item.get('is_dir', False)}")
            
            # Create the root folder
            root_name = bucket_name if not prefix else os.path.basename(prefix.rstrip('/'))
            structure = {
                "type": "folder",
                "name": root_name,
                "path": prefix,
                "children": []
            }
            
            # Add items to the structure
            for item in contents:
                if item.get("is_dir", False):
                    # For directories, recursively get their contents
                    child_structure = self.get_folder_structure(bucket_name, item["path"])
                    structure["children"].append(child_structure)
                else:
                    # For files, just add them to the structure
                    structure["children"].append({
                        "type": "file",
                        "name": item["name"],
                        "path": item["path"],
                        "size": item.get("size", 0),
                        "last_modified": item.get("last_modified", None)
                    })
            
            # Debug log the structure
            logger.info(f"DEBUG: Folder structure for '{bucket_name}' with prefix '{prefix}':")
            logger.info(f"  Type: {structure['type']}, Name: {structure['name']}, Path: {structure['path']}")
            logger.info(f"  Children: {len(structure['children'])}")
            for child in structure['children']:
                logger.info(f"    {child.get('name')} - type: {child.get('type')}")
                if child.get('type') == 'folder' and 'children' in child:
                    logger.info(f"      Contains: {len(child.get('children', []))} items")
            
            return structure
            
        except Exception as e:
            logger.error(f"Error getting folder structure for '{bucket_name}' with prefix '{prefix}': {str(e)}")
            return {"type": "folder", "name": bucket_name, "path": prefix, "children": []} 