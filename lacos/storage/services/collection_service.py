import logging
import os
import time
from typing import Dict, Any, List, Optional

from .base_storage_service import BaseStorageService
from .folder_cache_service import FolderStructureCacheService

logger = logging.getLogger(__name__)

class CollectionService(BaseStorageService):
    """
    Service for handling collection operations in S3/MinIO buckets.
    
    This service extends BaseStorageService to provide specialized functionality
    for working with collections, which have specific directory structure requirements.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(CollectionService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the CollectionService with base storage configuration.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if getattr(self, 'initialized', False):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        logger.debug("CollectionService initialized")
        self.initialized = True
        self._folder_cache = FolderStructureCacheService(timeout=300)
    
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
    
    def list_bucket_contents(
        self,
        bucket_name: str,
        prefix: str = "",
        *,
        force_fresh: bool = False,
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List the contents of a bucket with the given prefix.

        Args:
            bucket_name (str): The name of the bucket to list
            prefix (str, optional): The prefix (path) to list. Defaults to "".
            force_fresh (bool): Whether to bypass cached results.
            max_keys (int, optional): Maximum number of keys to return. If None, returns all.
            continuation_token (str, optional): Token to continue from previous request

        Returns:
            Dict[str, Any]: Dictionary with keys:
                - items: List of item dictionaries
                - has_more: Boolean indicating if more results available
                - next_token: Token for next page (if has_more is True)
        """
        try:
            logger.info("Listing contents of bucket '%s' with prefix '%s'", bucket_name, prefix)

            cache_path = prefix or ""
            if continuation_token:
                cache_path = f"{cache_path}::token::{continuation_token}"

            # Check cache first - this avoids expensive S3 calls
            if not force_fresh and not continuation_token:
                cache_check_start = time.monotonic()
                cached_result = self._folder_cache.get(bucket_name, cache_path)
                cache_check_duration = time.monotonic() - cache_check_start
                if cached_result is not None:
                    logger.info("📋 Found %d cached items for %s:%s (cache lookup: %.3fs, skipping S3 call)", 
                               len(cached_result.get("items", [])), bucket_name, prefix or "/", cache_check_duration)
                    return cached_result
                else:
                    logger.debug("Cache miss for %s:%s (cache lookup: %.3fs)", bucket_name, prefix or "/", cache_check_duration)
            elif force_fresh:
                logger.info("📋 Force fresh listing for %s:%s (cache bypassed)", bucket_name, prefix or "/")

            # Ensure prefix ends with / if it's not empty to avoid partial matches
            listing_prefix = prefix
            if listing_prefix and not listing_prefix.endswith('/'):
                listing_prefix = f"{listing_prefix}/"
                logger.debug("Adjusted prefix to '%s'", listing_prefix)

            contents: list[dict[str, Any]] = []
            started = time.monotonic()
            page_count = 0
            has_more = False
            next_token = None

            # Build pagination params
            list_params = {
                "Bucket": bucket_name,
                "Prefix": listing_prefix,
                "Delimiter": "/",
            }

            if max_keys:
                list_params["MaxKeys"] = max_keys

            if continuation_token:
                list_params["ContinuationToken"] = continuation_token

            # If max_keys is set, fetch only a single page
            if max_keys:
                logger.info("📦 S3 LIST: Calling list_objects_v2 for %s:%s (max_keys=%s)", 
                           bucket_name, listing_prefix or "/", max_keys)
                s3_call_start = time.monotonic()
                response = self.s3_client.list_objects_v2(**list_params)
                s3_call_duration = time.monotonic() - s3_call_start
                page_count = 1

                logger.info(
                    "📦 S3 LIST: Completed in %.3fs -> %s objects, %s prefixes",
                    s3_call_duration,
                    len(response.get("Contents", [])),
                    len(response.get("CommonPrefixes", [])),
                )

                for obj in response.get("Contents", []):
                    # Skip the directory marker itself if listing a directory
                    if listing_prefix and obj["Key"] == listing_prefix:
                        continue

                    contents.append(
                        {
                            "name": os.path.basename(obj["Key"]),
                            "path": obj["Key"],
                            "size": obj.get("Size"),
                            "last_modified": obj.get("LastModified"),
                            "is_dir": False,
                        }
                    )

                for prefix_obj in response.get("CommonPrefixes", []):
                    prefix_str = prefix_obj.get("Prefix", "")
                    contents.append(
                        {
                            "name": os.path.basename(prefix_str.rstrip("/")),
                            "path": prefix_str,
                            "is_dir": True,
                        }
                    )

                has_more = response.get("IsTruncated", False)
                next_token = response.get("NextContinuationToken")
            else:
                # Legacy mode: paginate through all results
                paginator = self.s3_client.get_paginator('list_objects_v2')

                for page in paginator.paginate(**list_params):
                    page_count += 1
                    logger.debug(
                        "S3 page %s for %s:%s -> %s objects, %s prefixes",
                        page_count,
                        bucket_name,
                        listing_prefix or "/",
                        len(page.get("Contents", [])),
                        len(page.get("CommonPrefixes", [])),
                    )
                    for obj in page.get("Contents", []):
                        # Skip the directory marker itself if listing a directory
                        if listing_prefix and obj["Key"] == listing_prefix:
                            continue

                        contents.append(
                            {
                                "name": os.path.basename(obj["Key"]),
                                "path": obj["Key"],
                                "size": obj.get("Size"),
                                "last_modified": obj.get("LastModified"),
                                "is_dir": False,
                            }
                        )

                    for prefix_obj in page.get("CommonPrefixes", []):
                        prefix_str = prefix_obj.get("Prefix", "")
                        contents.append(
                            {
                                "name": os.path.basename(prefix_str.rstrip("/")),
                                "path": prefix_str,
                                "is_dir": True,
                            }
                        )

            preview = ', '.join(item["name"] for item in contents[:5])
            logger.debug(
                "Listed %s items for %s%s",
                len(contents),
                listing_prefix or f"{bucket_name}/",
                f" — {preview}" if preview else "",
            )
            logger.info(
                "Completed listing for %s:%s in %.2fs (%s pages, %s total items, has_more=%s)",
                bucket_name,
                listing_prefix or "/",
                time.monotonic() - started,
                page_count,
                len(contents),
                has_more,
            )

            result = {
                "items": contents,
                "has_more": has_more,
                "next_token": next_token,
            }

            # Cache the results for 5 minutes (300 seconds)
            if not continuation_token:
                cache_set_start = time.monotonic()
                self._folder_cache.set(bucket_name, cache_path, result)
                cache_set_duration = time.monotonic() - cache_set_start
                logger.info("📋 Cached %d items for %s:%s (cache set: %.3fs, TTL: 300s)", 
                           len(contents), bucket_name, prefix or "/", cache_set_duration)

            return result
        except Exception as e:
            logger.error(
                f"Error listing bucket contents for bucket: '{bucket_name}'. Error: {e}"
            )
            return {"items": [], "has_more": False, "next_token": None}
    
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
            # list_bucket_contents now returns a dict
            listing_result = self.list_bucket_contents(bucket_name, prefix)
            contents = listing_result.get("items", [])

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
