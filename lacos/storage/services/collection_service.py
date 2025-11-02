import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

from .base_storage_service import BaseStorageService
from .folder_cache_service import FolderStructureCacheService
from lacos.storage.observability import record_cache_event, record_s3_listing_page

logger = logging.getLogger(__name__)


@dataclass
class BucketListingPage(Sequence[Dict[str, Any]]):
    """Paginated listing response that behaves like a list for legacy callers."""

    items: List[Dict[str, Any]] = field(default_factory=list)
    has_more: bool = False
    next_token: Optional[str] = None
    bucket: Optional[str] = None
    prefix: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: Union[int, slice]) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        return self.items[index]

    def __bool__(self) -> bool:
        return bool(self.items)

    def as_list(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the item list."""
        return list(self.items)

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
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
        force_fresh: bool = False,
    ) -> BucketListingPage:
        """
        List the contents of a bucket with the given prefix.
        
        Args:
            bucket_name (str): The name of the bucket to list
            prefix (str, optional): The prefix (path) to list. Defaults to "".
            max_keys (int, optional): Maximum number of keys to return for lazy loading.
            continuation_token (str, optional): S3 continuation token for pagination.
            
        Returns:
            BucketListingPage: Paginated results including continuation metadata.
        """
        try:
            logger.info("Listing contents of bucket '%s' with prefix '%s'", bucket_name, prefix)

            paginated = max_keys is not None or continuation_token is not None
            cached_response: Optional[BucketListingPage] = None

            if not paginated and not force_fresh:
                cached = self._folder_cache.get(bucket_name, prefix)
                if cached is not None:
                    logger.debug("Returning cached listing for %s:%s", bucket_name, prefix)
                    record_cache_event(
                        event="folder_listing",
                        bucket=bucket_name,
                        prefix=prefix,
                        hit=True,
                        metadata={"source": "collection_service"},
                    )
                    return cached
            if not paginated:
                record_cache_event(
                    event="folder_listing",
                    bucket=bucket_name,
                    prefix=prefix,
                    hit=False,
                    metadata={
                        "source": "collection_service",
                        "forced": force_fresh,
                        "paginated": False,
                    },
                )

            # Ensure prefix ends with / if it's not empty to avoid partial matches
            listing_prefix = prefix
            if listing_prefix and not listing_prefix.endswith('/'):
                listing_prefix = f"{listing_prefix}/"
                logger.debug("Adjusted prefix to '%s'", listing_prefix)

            pages: List[Dict[str, Any]] = []
            last_page: Dict[str, Any] = {}

            if paginated:
                params = {
                    "Bucket": bucket_name,
                    "Prefix": listing_prefix,
                    "Delimiter": "/",
                }
                if max_keys is not None:
                    params["MaxKeys"] = max_keys
                if continuation_token:
                    params["ContinuationToken"] = continuation_token
                page_start = time.perf_counter()
                response = self.s3_client.list_objects_v2(**params)
                duration_ms = (time.perf_counter() - page_start) * 1000
                page_key_count = len(response.get("Contents", [])) + len(response.get("CommonPrefixes", []))
                page_size_bytes = sum(obj.get("Size") or 0 for obj in response.get("Contents", []))
                record_s3_listing_page(
                    bucket=bucket_name,
                    prefix=listing_prefix or "",
                    key_count=page_key_count,
                    size_bytes=page_size_bytes,
                    duration_ms=duration_ms,
                    continuation_token=response.get("NextContinuationToken"),
                    is_truncated=response.get("IsTruncated", False),
                    cache_hit=False,
                )
                pages.append(response)
                last_page = response
            else:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket_name, Prefix=listing_prefix, Delimiter="/"):
                    page_start = time.perf_counter()
                    pages.append(page)
                    page_key_count = len(page.get("Contents", [])) + len(page.get("CommonPrefixes", []))
                    page_size_bytes = sum(obj.get("Size") or 0 for obj in page.get("Contents", []))
                    duration_ms = (time.perf_counter() - page_start) * 1000
                    record_s3_listing_page(
                        bucket=bucket_name,
                        prefix=listing_prefix or "",
                        key_count=page_key_count,
                        size_bytes=page_size_bytes,
                        duration_ms=duration_ms,
                        continuation_token=page.get("NextContinuationToken"),
                        is_truncated=page.get("IsTruncated", False),
                        cache_hit=False,
                    )
                    last_page = page

            items: List[Dict[str, Any]] = []
            for page in pages:
                for obj in page.get("Contents", []):
                    if listing_prefix and obj["Key"] == listing_prefix:
                        continue
                    items.append(
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
                    items.append(
                        {
                            "name": os.path.basename(prefix_str.rstrip("/")),
                            "path": prefix_str,
                            "is_dir": True,
                        }
                    )

            preview = ', '.join(item["name"] for item in items[:5])
            logger.debug(
                "Listed %s items for %s%s",
                len(items),
                listing_prefix or f"{bucket_name}/",
                f" — {preview}" if preview else "",
            )

            listing = BucketListingPage(
                items=items,
                has_more=bool(last_page.get("IsTruncated")),
                next_token=last_page.get("NextContinuationToken"),
                bucket=bucket_name,
                prefix=prefix,
                raw_response=last_page or {},
            )

            if not paginated:
                self._folder_cache.set(bucket_name, prefix, listing)

            return listing
        except Exception as e:
            logger.error(
                f"Error listing bucket contents for bucket: '{bucket_name}'. Error: {e}"
            )
            return BucketListingPage(items=[], has_more=False, next_token=None, bucket=bucket_name, prefix=prefix)
    
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
