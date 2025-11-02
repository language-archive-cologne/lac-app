"""
Bucket listing service for storage operations.

This service handles fetching folder contents, pagination, and cache operations
for S3/MinIO bucket listings. It collaborates with CollectionService for raw
S3 operations and FolderStructureCacheService for caching.
"""
import logging
import time
from typing import Dict, List, Optional, Any

from .service_context import StorageServiceContext
from .collection_service import CollectionService, BucketListingPage
from lacos.storage.observability import get_current_session

logger = logging.getLogger(__name__)


class BucketListingService:
    """
    Service for listing and paginating bucket/folder contents.

    Handles cache reads/writes, pagination, and returns parsed BucketListingPage
    responses. Does not perform metadata enrichment (that's handled separately).
    """

    def __init__(self, context: StorageServiceContext, collection_service: CollectionService):
        """
        Initialize the listing service.

        Args:
            context: Shared service context
            collection_service: Collection service for raw S3 operations
        """
        self.context = context
        self.collection_service = collection_service

    def get_root_level_items(
        self, bucket_name: str, force_fresh: bool = False
    ) -> Dict[str, Any]:
        """
        Get only the root level items (files and folders) from a bucket.
        Optimized for initial dashboard load.

        Args:
            bucket_name: The name of the bucket to list
            force_fresh: Force bypass cache and fetch fresh data

        Returns:
            Dict[str, Any]: Dictionary containing root level items
        """
        start_time = time.perf_counter()
        session = get_current_session()
        operation_meta = None

        if session:
            operation_meta = {
                "operation": "get_root_level_items",
                "bucket": bucket_name,
                "force_fresh": force_fresh,
                "cache_hit": False,
            }
            session.metadata.setdefault("bucket_service_calls", []).append(operation_meta)

        try:
            # Try cache first unless force_fresh
            if not force_fresh:
                cached = self.context.folder_cache.get(bucket_name, None)
                if cached is not None:
                    if operation_meta is not None:
                        operation_meta.update(
                            {
                                "cache_hit": True,
                                "items": len(cached),
                                "has_more": getattr(cached, "has_more", False),
                                "next_token": getattr(cached, "next_token", None),
                            }
                        )
                    return cached

            # Fetch from S3 using collection service
            listing_page = self.collection_service.list_bucket_contents(
                bucket_name, "", force_fresh=force_fresh
            )

            # Build simplified result structure
            result = {
                "items": listing_page.items,
                "has_more": listing_page.has_more,
                "next_token": listing_page.next_token,
                "bucket": bucket_name,
                "prefix": "",
            }

            # Cache the result
            self.context.folder_cache.set(bucket_name, None, result)

            if operation_meta is not None:
                operation_meta.update(
                    {
                        "items": len(listing_page.items),
                        "cache_hit": False,
                        "has_more": listing_page.has_more,
                        "next_token": listing_page.next_token,
                    }
                )

            return result

        except Exception as e:
            logger.error(
                f"Error getting root level items from bucket '{bucket_name}': {str(e)}"
            )
            if operation_meta is not None:
                operation_meta["error"] = str(e)
            return {
                "items": [],
                "has_more": False,
                "next_token": None,
                "bucket": bucket_name,
                "prefix": "",
            }
        finally:
            if operation_meta is not None:
                operation_meta["duration_ms"] = round(
                    (time.perf_counter() - start_time) * 1000, 3
                )

    def get_folder_contents(
        self,
        bucket_name: str,
        folder_path: str,
        *,
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
        force_fresh: bool = False,
    ) -> BucketListingPage:
        """
        Get the contents of a specific folder.
        Used for lazy loading folder contents.

        Args:
            bucket_name: The name of the bucket
            folder_path: The path to the folder
            max_keys: Maximum number of items to return (for pagination)
            continuation_token: Token for fetching next page
            force_fresh: Force bypass cache and fetch fresh data

        Returns:
            BucketListingPage: Paginated listing of items in the folder
        """
        start_time = time.perf_counter()
        session = get_current_session()
        operation_meta = None

        if session:
            operation_meta = {
                "operation": "get_folder_contents",
                "bucket": bucket_name,
                "folder_path": folder_path,
                "max_keys": max_keys,
                "continuation_token": continuation_token,
                "force_fresh": force_fresh,
                "cache_hit": False,
            }
            session.metadata.setdefault("bucket_service_calls", []).append(operation_meta)

        try:
            # Check if this is a paginated request
            paginated = max_keys is not None or continuation_token is not None

            # Try cache for non-paginated requests
            if not paginated and not force_fresh:
                cached = self.context.folder_cache.get(bucket_name, folder_path)
                if cached is not None:
                    if operation_meta is not None:
                        operation_meta.update(
                            {
                                "cache_hit": True,
                                "items": len(cached),
                                "has_more": getattr(cached, "has_more", False),
                                "next_token": getattr(cached, "next_token", None),
                            }
                        )
                    return cached

            # Fetch from S3 using collection service
            listing_page = self.collection_service.list_bucket_contents(
                bucket_name,
                folder_path,
                max_keys=max_keys,
                continuation_token=continuation_token,
                force_fresh=force_fresh,
            )

            # Cache non-paginated results
            if not paginated:
                self.context.folder_cache.set(bucket_name, folder_path, listing_page)

            if operation_meta is not None:
                operation_meta.update(
                    {
                        "items": len(listing_page),
                        "cache_hit": False,
                        "has_more": listing_page.has_more,
                        "next_token": listing_page.next_token,
                    }
                )

            return listing_page

        except Exception as e:
            logger.error(
                f"Error getting folder contents for '{folder_path}' in bucket '{bucket_name}': {str(e)}"
            )
            if operation_meta is not None:
                operation_meta["error"] = str(e)
            return BucketListingPage(
                items=[],
                has_more=False,
                next_token=None,
                bucket=bucket_name,
                prefix=folder_path,
            )
        finally:
            if operation_meta is not None:
                operation_meta["duration_ms"] = round(
                    (time.perf_counter() - start_time) * 1000, 3
                )

    def invalidate_folder_cache(
        self, bucket_name: str, *folder_paths: Optional[str]
    ) -> None:
        """
        Invalidate cached folder contents.

        Args:
            bucket_name: The bucket name
            folder_paths: Variable number of folder paths to invalidate (None = root)
        """
        for path in folder_paths:
            self.context.folder_cache.delete(bucket_name, path)
            logger.debug(
                f"Invalidated cache for bucket '{bucket_name}', path '{path or 'root'}'"
            )
