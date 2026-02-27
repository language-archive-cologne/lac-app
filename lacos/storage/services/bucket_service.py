import logging
import os
from typing import Any, Dict, List, Optional, Set
import shutil
import tempfile
from pathlib import Path
import time

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.cache import cache
import boto3
from django.core.management import call_command


from .base_storage_service import BaseStorageService
from .collection_service import CollectionService, BucketListingPage
from .upload_service import UploadService
from .ocfl_service import OCFLService
from .folder_cache_service import FolderStructureCacheService
from .service_context import StorageServiceContext
from .bucket_listing_service import BucketListingService
from .bucket_metadata_service import BucketMetadataService
from .bucket_mutation_service import BucketMutationService
from lacos.storage.observability import get_current_session

# Import BLAM models for direct access
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

logger = logging.getLogger(__name__)


class BucketService(BaseStorageService):
    """
    Primary service for interacting with S3/MinIO buckets.
    
    This service delegates to specialized services for specific functionality
    while providing a unified interface for the application.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BucketService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the BucketService with all required sub-services.

        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return

        super().__init__(skip_bucket_check=skip_bucket_check)

        # Initialize the specialized services with skip_bucket_check=True
        self.collection_service = CollectionService(skip_bucket_check=True)
        self.upload_service = UploadService(skip_bucket_check=True)

        # Configure child services with consistent settings
        self.set_client_and_buckets(self.collection_service)
        self.set_client_and_buckets(self.upload_service)

        # Initialize OCFL service after other services are ready
        self.ocfl_service = OCFLService(self)
        # OCFL service uses this instance's bucket references, so just set the client
        if hasattr(self.ocfl_service, 's3_client'):
            self.ocfl_service.s3_client = self.s3_client

        # Per-bucket folder cache helper
        self.folder_cache = FolderStructureCacheService()

        # Dashboard pagination controls
        self.dashboard_pagination_enabled = getattr(settings, "STORAGE_DASHBOARD_PAGINATION_ENABLED", True)
        self.dashboard_page_size = getattr(settings, "STORAGE_DASHBOARD_PAGE_SIZE", 200)

        # Create shared service context
        self._service_context = StorageServiceContext.from_base_service(self)

        # Initialize new helper services
        self._listing_service = BucketListingService(self._service_context, self.collection_service)
        self._metadata_service = BucketMetadataService(self._service_context, self.collection_service)
        self._mutation_service = BucketMutationService(self._service_context)

        logger.info("BucketService initialized with helper services")
        self.initialized = True

    def _download_directory(self, bucket_name: str, prefix: str, local_dir: str) -> None:
        """Download an S3 prefix to a local directory."""
        paginator = self.s3_client.get_paginator("list_objects_v2")
        normalized_prefix = prefix if not prefix or prefix.endswith('/') else f"{prefix}/"

        for page in paginator.paginate(Bucket=bucket_name, Prefix=normalized_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if normalized_prefix and key == normalized_prefix:
                    continue

                rel_path = key[len(normalized_prefix):] if normalized_prefix else key
                target_path = os.path.join(local_dir, rel_path)
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                self.s3_client.download_file(bucket_name, key, target_path)

    def _upload_directory(self, local_dir: str, bucket_name: str, target_prefix: str) -> Dict[str, Any]:
        """Upload a local directory into an S3 prefix."""
        prefix = target_prefix if not target_prefix or target_prefix.endswith('/') else f"{target_prefix}/"

        for root, _, files in os.walk(local_dir):
            for file in files:
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, local_dir).replace(os.sep, '/')
                dest_key = f"{prefix}{rel_path}" if prefix else rel_path
                self.s3_client.upload_file(src_path, bucket_name, dest_key)

        return {"success": True}
    
    def is_blam_object(self, bucket_name: str, path: str) -> Dict[str, Any]:
        """
        Check if a path corresponds to a BLAM model (Collection or Bundle).

        Delegates to BucketMetadataService.

        Args:
            bucket_name (str): The bucket name
            path (str): The path to check

        Returns:
            Dict with keys:
                is_blam_object (bool): Whether this is a BLAM object
                blam_type (str, optional): "collection" or "bundle" if applicable
                blam_id (str, optional): The database ID if applicable
        """
        return self._metadata_service.is_blam_object(bucket_name, path)
    
    def get_root_level_items(self, bucket_name: str, force_fresh: bool = False) -> Dict[str, Any]:
        """
        Get only the root level items (files and folders) from a bucket.
        This is optimized for the initial dashboard load.

        Delegates to BucketListingService and BucketMetadataService.

        Args:
            bucket_name (str): The name of the bucket to list
            force_fresh (bool): Force bypass cache

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
            if not force_fresh:
                cached = self.folder_cache.get(bucket_name, None)
                if cached is not None:
                    if operation_meta is not None:
                        operation_meta.update(
                            {
                                "cache_hit": True,
                                "children": len(cached.get("children", [])),
                            }
                        )
                    return cached

            # Get listing from listing service
            contents = self.collection_service.list_bucket_contents(
                bucket_name,
                force_fresh=force_fresh,
            )

            # Enrich with BLAM metadata
            folder_items = [entry for entry in contents if entry.get("is_dir")]
            blam_metadata = self._metadata_service.build_blam_metadata_index(bucket_name, folder_items)

            # Process items to add BLAM object information
            processed_children = []
            for item in contents:
                parent_info = self._split_parent_child(item["path"])

                child = {
                    "type": "folder" if item["is_dir"] else "file",
                    "name": item["name"],
                    "path": item["path"],
                    "parent_path": parent_info["parent"],
                    "size": item.get("size"),
                    "last_modified": item.get("last_modified"),
                }

                if item["is_dir"]:
                    blam_info = blam_metadata.get(item["path"])
                    if blam_info:
                        child.update(blam_info)

                processed_children.append(child)

            # Transform the contents into the expected structure
            result = {
                "type": "folder",
                "name": bucket_name,
                "path": "",
                "children": processed_children
            }
            self.folder_cache.set(bucket_name, None, result)
            if operation_meta is not None:
                operation_meta.update(
                    {
                        "children": len(processed_children),
                        "cache_hit": False,
                    }
                )
            return result
        except Exception as e:
            logger.error("Error getting root level items for bucket", extra={"bucket_name": bucket_name, "error": str(e)})
            if operation_meta is not None:
                operation_meta["error"] = str(e)
            return {"type": "folder", "name": bucket_name, "path": "", "children": []}
        finally:
            if operation_meta is not None:
                operation_meta["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 3)

    def get_folder_contents(
        self,
        bucket_name: str,
        folder_path: str,
        *,
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
        force_fresh: bool = False,
        raise_errors: bool = False,
    ) -> BucketListingPage:
        """
        Get the contents of a specific folder.
        This is used for lazy loading folder contents.

        Delegates to BucketListingService and BucketMetadataService.

        Args:
            bucket_name (str): The name of the bucket
            folder_path (str): The path to the folder
            max_keys (int, optional): Maximum number of items to return
            continuation_token (str, optional): Token for pagination
            force_fresh (bool): Force bypass cache
            raise_errors (bool): Re-raise listing errors instead of returning an empty page

        Returns:
            BucketListingPage: Paginated list of items in the folder
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
                "raise_errors": raise_errors,
                "cache_hit": False,
            }
            session.metadata.setdefault("bucket_service_calls", []).append(operation_meta)
        try:
            paginated = max_keys is not None or continuation_token is not None
            if not paginated and not force_fresh:
                cached = self.folder_cache.get(bucket_name, folder_path)
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

            # Get listing from collection service
            listing_page = self.collection_service.list_bucket_contents(
                bucket_name,
                folder_path,
                max_keys=max_keys,
                continuation_token=continuation_token,
                force_fresh=force_fresh,
                raise_errors=raise_errors,
            )

            # Enrich with BLAM metadata
            folder_items = [entry for entry in listing_page if entry.get("is_dir")]
            blam_metadata = self._metadata_service.build_blam_metadata_index(bucket_name, folder_items)

            # Transform the contents and add BLAM object information
            processed_contents = []
            for item in listing_page:
                parent_info = self._split_parent_child(item["path"])

                result = {
                    "type": "folder" if item["is_dir"] else "file",
                    "name": item["name"],
                    "path": item["path"],
                    "parent_path": parent_info["parent"],
                    "size": item.get("size"),
                    "last_modified": item.get("last_modified"),
                }

                if item["is_dir"]:
                    blam_info = blam_metadata.get(item["path"])
                    if blam_info:
                        result.update(blam_info)

                processed_contents.append(result)

            result_page = BucketListingPage(
                items=processed_contents,
                has_more=listing_page.has_more,
                next_token=listing_page.next_token,
                bucket=bucket_name,
                prefix=folder_path,
                raw_response=listing_page.raw_response,
            )

            if not paginated:
                self.folder_cache.set(bucket_name, folder_path, result_page)

            if operation_meta is not None:
                operation_meta.update(
                    {
                        "items": len(processed_contents),
                        "cache_hit": False,
                        "has_more": listing_page.has_more,
                        "next_token": listing_page.next_token,
                    }
                )
            return result_page
        except Exception as e:
            logger.error("Error getting folder contents", extra={"folder_path": folder_path, "bucket_name": bucket_name, "error": str(e)})
            if operation_meta is not None:
                operation_meta["error"] = str(e)
            if raise_errors:
                raise
            return BucketListingPage(items=[], has_more=False, next_token=None, bucket=bucket_name, prefix=folder_path)
        finally:
            if operation_meta is not None:
                operation_meta["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 3)

    def _build_blam_metadata_index(
        self,
        bucket_name: str,
        folder_items: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build a lookup of BLAM metadata for a collection of folder entries.

        DEPRECATED: Delegates to BucketMetadataService.

        Args:
            bucket_name: The bucket being inspected.
            folder_items: Folder entries returned from S3.

        Returns:
            Mapping of folder path -> BLAM metadata dict.
        """
        return self._metadata_service.build_blam_metadata_index(bucket_name, folder_items)

    def _invalidate_folder_cache(self, bucket_name: str, *folder_paths: Optional[str]) -> None:
        try:
            if folder_paths:
                self.folder_cache.invalidate_many(bucket_name, *folder_paths)
            else:
                self.folder_cache.invalidate(bucket_name)
        except Exception as exc:
            logger.debug("Cache invalidation skipped for %s (%s)", bucket_name, exc)

    # Collection-related methods
    def is_collection_path(self, path: str) -> bool:
        """Delegate to collection service to check if a path is a collection."""
        return self.collection_service.is_collection_path(path)
    
    def get_collection_parent_path(self, path: str) -> str:
        """Delegate to collection service to get the parent path of a collection."""
        return self.collection_service.get_collection_parent_path(path)
    
    def is_ocfl_object(self, bucket_name: str, prefix: str) -> bool:
        """Delegate to collection service to check if a path is an OCFL object."""
        return self.collection_service.is_ocfl_object(bucket_name, prefix)
    
    def find_ocfl_objects(self, bucket_name: str, prefix: str = "") -> List[str]:
        """Delegate to collection service to find all OCFL objects in a bucket/prefix."""
        return self.collection_service.find_ocfl_objects(bucket_name, prefix)

    # -------------------------------------------------------------------------
    # Rename operations
    # -------------------------------------------------------------------------

    def _is_valid_bucket_name(self, bucket_name: str) -> bool:
        """Validate bucket name allowing letters, numbers, hyphens, and underscores."""
        if not bucket_name:
            return False
        sanitized = bucket_name.replace('-', '').replace('_', '')
        return sanitized.isalnum()

    def _split_parent_child(self, path: str) -> Dict[str, str]:
        """Return parent prefix and child name for a given S3 path."""
        if not path:
            return {"parent": "", "name": ""}

        normalized = path.strip('/')
        if not normalized:
            return {"parent": "", "name": ""}

        if '/' not in normalized:
            return {"parent": "", "name": normalized}

        parent, name = normalized.rsplit('/', 1)
        return {"parent": f"{parent}/", "name": name}

    def rename_bucket(self, current_bucket: str, new_bucket: str) -> Dict[str, Any]:
        """
        Rename a bucket by copying all objects to a new bucket and deleting the old one.

        Delegates to BucketMutationService with bucket list management.
        """
        # Validate bucket accessibility before delegating
        accessible = self.get_all_accessible_buckets()
        if current_bucket.strip() not in accessible:
            return {"success": False, "error": f"Bucket '{current_bucket}' is not accessible"}

        if new_bucket.strip() in accessible:
            return {"success": False, "error": f"Bucket '{new_bucket}' already exists"}

        # Ensure new bucket exists
        if not self.ensure_bucket_exists(new_bucket.strip()):
            return {"success": False, "error": f"Failed to create bucket '{new_bucket}'"}

        # Delegate to mutation service
        result = self._mutation_service.rename_bucket(current_bucket, new_bucket)

        # Update in-memory workspace buckets if successful
        if result.get("success"):
            current = current_bucket.strip()
            new = new_bucket.strip()
            if current in self.workspace_buckets:
                self.workspace_buckets = [
                    new if b == current else b for b in self.workspace_buckets
                ]
            elif new not in self.workspace_buckets:
                self.workspace_buckets.append(new)

        return result

    def rename_folder(self, bucket_name: str, old_path: str, new_name: str) -> Dict[str, Any]:
        """
        Rename a folder within a bucket by copying to a new prefix and deleting the old.

        Delegates to BucketMutationService.
        """
        return self._mutation_service.rename_folder(bucket_name, old_path, new_name)

    def rename_file(self, bucket_name: str, file_path: str, new_name: str) -> Dict[str, Any]:
        """
        Rename a single file within a bucket.

        Delegates to BucketMutationService.
        """
        return self._mutation_service.rename_file(bucket_name, file_path, new_name)
    
    def list_bucket_contents(
        self,
        bucket_name: str,
        prefix: str = "",
        *,
        max_keys: Optional[int] = None,
        continuation_token: Optional[str] = None,
        force_fresh: bool = False,
    ) -> BucketListingPage:
        """Delegate to collection service to list bucket contents."""
        return self.collection_service.list_bucket_contents(
            bucket_name,
            prefix,
            max_keys=max_keys,
            continuation_token=continuation_token,
            force_fresh=force_fresh,
        )
    
    def get_folder_structure(self, bucket_name: str, prefix: str = "") -> Dict[str, Any]:
        """Delegate to collection service to get folder structure."""
        return self.collection_service.get_folder_structure(bucket_name, prefix)
    
    
    # OCFL-related methods
    def move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """Move a folder from the ingest bucket to the production bucket using the OCFL service."""
        logger.info("Starting move to production", extra={"source_prefix": source_prefix})
        return self.ocfl_service.move_to_production(source_prefix)
        
    def direct_move_to_production(self, source_prefix: str) -> Dict[str, Any]:
        """
        Move a folder from the ingest bucket to the production bucket directly without any transformation.
        This bypasses the OCFL service completely and just copies the files as they are.
        
        Args:
            source_prefix (str): The path in the ingest bucket to move
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        logger.info("Starting direct move to production", extra={"source_prefix": source_prefix})
        
        try:
            # Verify ingest and production buckets are different
            if self.ingest_bucket == self.production_bucket:
                error_message = "Error: Ingest and production buckets must be different"
                logger.error(error_message)
                return {
                    "success": False,
                    "error": error_message
                }
            
            # Ensure source_prefix ends with a slash for proper prefix matching
            if not source_prefix.endswith('/'):
                source_prefix = source_prefix + '/'
                logger.info("Added trailing slash for proper prefix matching", extra={"source_prefix": source_prefix})
            
            # List all objects in the source
            paginator = self.s3_client.get_paginator("list_objects_v2")
            copied_files = 0
            
            for page in paginator.paginate(Bucket=self.ingest_bucket, Prefix=source_prefix):
                for obj in page.get("Contents", []):
                    source_key = obj["Key"]
                    
                    # Skip if this is just the folder marker object
                    if source_key == source_prefix:
                        logger.info("Skipping folder marker object", extra={"source_key": source_key})
                        continue
                    
                    # Copy the object to the production bucket
                    self.s3_client.copy_object(
                        CopySource={"Bucket": self.ingest_bucket, "Key": source_key},
                        Bucket=self.production_bucket,
                        Key=source_key
                    )
                    
                    copied_files += 1
                    
                    if copied_files % 10 == 0:
                        logger.info("Copy progress", extra={"copied_files": copied_files})
            
            # Add an empty directory marker if no files were found
            if copied_files == 0:
                logger.warning("No files found to copy, creating an empty directory marker", extra={"source_prefix": source_prefix})
                self.s3_client.put_object(
                    Bucket=self.production_bucket,
                    Key=source_prefix,
                    Body=''
                )
                copied_files = 1
            
            if copied_files > 0:
                logger.info("Successfully copied files to production bucket", extra={"copied_files": copied_files, "source_prefix": source_prefix})
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to production bucket ({copied_files} files copied)"
                }
            else:
                # This should never happen now due to the empty directory marker
                logger.warning("No files found to copy", extra={"source_prefix": source_prefix})
                return {
                    "success": False,
                    "error": f"No files found to copy at {source_prefix}"
                }
                
        except Exception as e:
            logger.error("Error in direct_move_to_production", extra={"error": str(e)})
        return {
            "success": False,
            "error": str(e)
        }

    def get_bucket_total_size(self, bucket_name: str, force_fresh: bool = False) -> Dict[str, Any]:
        """Calculate total size and object count for a bucket."""
        cache_key = f"storage_bucket_size_{bucket_name}"

        if not force_fresh:
            cached_result = cache.get(cache_key)
            if cached_result:
                return cached_result

        start_time = time.time()
        total_size = 0
        object_count = 0

        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")

            for page in paginator.paginate(Bucket=bucket_name):
                contents = page.get("Contents", [])
                object_count += len(contents)
                total_size += sum(obj.get("Size", 0) for obj in contents)

            duration = time.time() - start_time
            result = {
                "success": True,
                "bucket_name": bucket_name,
                "total_size": total_size,
                "total_size_formatted": self._format_size(total_size),
                "object_count": object_count,
                "calculation_duration": duration,
            }

            cache.set(cache_key, result, timeout=1800)
            return result

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.error("Error calculating bucket size", extra={"bucket_name": bucket_name, "error_code": error_code})
            return {
                "success": False,
                "bucket_name": bucket_name,
                "error": f"S3 error: {error_code}",
                "total_size": 0,
                "total_size_formatted": "0 B",
                "object_count": 0,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error calculating bucket size", extra={"bucket_name": bucket_name})
            return {
                "success": False,
                "bucket_name": bucket_name,
                "error": str(exc),
                "total_size": 0,
                "total_size_formatted": "0 B",
                "object_count": 0,
            }

    def get_file_info(self, bucket_name: str, object_path: str) -> Dict[str, Any]:
        """Fetch metadata for a single object."""
        try:
            metadata = self.s3_client.head_object(Bucket=bucket_name, Key=object_path)
            size = metadata.get("ContentLength", 0)
            last_modified = metadata.get("LastModified")

            return {
                "success": True,
                "bucket_name": bucket_name,
                "object_path": object_path,
                "file_name": os.path.basename(object_path.rstrip("/")),
                "file_size": size,
                "file_size_formatted": self._format_size(size),
                "content_type": metadata.get("ContentType", "application/octet-stream"),
                "last_modified": last_modified.isoformat() if last_modified else None,
                "etag": metadata.get("ETag"),
                "metadata": metadata.get("Metadata", {}),
            }
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if error_code == "NoSuchKey" or status_code == 404:
                logger.warning("File not found for info lookup", extra={"object_path": object_path})
                error_message = "File not found"
            else:
                logger.error("Error fetching file info", extra={"object_path": object_path, "error_code": error_code})
                error_message = f"S3 error: {error_code}"

            return {
                "success": False,
                "bucket_name": bucket_name,
                "object_path": object_path,
                "error": error_message,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error fetching file info", extra={"object_path": object_path})
            return {
                "success": False,
                "bucket_name": bucket_name,
                "object_path": object_path,
                "error": str(exc),
            }

    def generate_presigned_download_url(
        self,
        bucket_name: str,
        object_path: str,
        expires_in: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a presigned GET URL for streaming/downloading an object.

        Args:
            bucket_name: S3 bucket name
            object_path: S3 object key
            expires_in: URL expiration in seconds (default from settings.PRESIGNED_URL_EXPIRATION)

        Returns:
            Dict with 'success', 'url', and 'expires_in' on success,
            or 'success' and 'error' on failure.
        """
        if expires_in is None:
            expires_in = getattr(settings, 'PRESIGNED_URL_EXPIRATION', 3600)

        client = getattr(self, "presigned_client", self.s3_client)

        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": object_path,
                },
                ExpiresIn=expires_in,
            )

            return {
                "success": True,
                "url": url,
                "expires_in": expires_in,
            }
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                "Error generating presigned URL for %s: %s",
                object_path,
                error_code,
            )
            return {
                "success": False,
                "error": f"S3 error: {error_code}",
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(
                "Unexpected error generating presigned URL for %s", object_path
            )
            return {
                "success": False,
                "error": str(exc),
            }
        
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def delete_folder(self, bucket_name, folder_path):
        """
        Delete a folder and all its contents from the specified bucket.

        Delegates to BucketMutationService.

        Args:
            bucket_name: The name of the bucket
            folder_path: Path to the folder to delete

        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self._mutation_service.delete_folder(bucket_name, folder_path)

    def delete_file(self, bucket_name, file_path):
        """
        Delete a single file from the specified bucket.

        Delegates to BucketMutationService.

        Args:
            bucket_name: The name of the bucket
            file_path: Path to the file to delete

        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self._mutation_service.delete_file(bucket_name, file_path)

    def create_bucket(self, bucket_name: str, enable_ocfl: bool = False) -> Dict[str, Any]:
        """
        Create a new bucket and add it to the workspace buckets.

        Args:
            bucket_name (str): Name of the bucket to create
            enable_ocfl (bool): Whether to enable OCFL operations on this bucket

        Returns:
            Dict[str, Any]: Result with success status and message
        """
        logger.info("Creating new bucket", extra={"bucket_name": bucket_name, "enable_ocfl": enable_ocfl})

        try:
            # Validate bucket name
            if not bucket_name or not bucket_name.replace('-', '').replace('_', '').isalnum():
                return {
                    "success": False,
                    "error": "Invalid bucket name. Use only letters, numbers, hyphens, and underscores."
                }

            # Check if bucket already exists in workspace
            if bucket_name in self.workspace_buckets:
                return {
                    "success": False,
                    "error": f"Bucket '{bucket_name}' already exists in workspace."
                }

            # Create the bucket using the base service method
            bucket_created = self.ensure_bucket_exists(bucket_name)

            if not bucket_created:
                return {
                    "success": False,
                    "error": f"Failed to create bucket '{bucket_name}'"
                }

            # Add to workspace buckets list (in-memory for this session)
            # Note: For persistent storage, this would need to be saved to database or config
            self.workspace_buckets.append(bucket_name)

            # Add to OCFL buckets if requested
            if enable_ocfl and bucket_name not in self.ocfl_buckets:
                self.ocfl_buckets.append(bucket_name)

            # Invalidate the bucket list cache so new bucket appears immediately
            cache.delete("storage:bucket-names")
            logger.info("Successfully created bucket and added to workspace", extra={"bucket_name": bucket_name})

            return {
                "success": True,
                "message": f"Bucket '{bucket_name}' created successfully",
                "bucket_name": bucket_name,
                "ocfl_enabled": enable_ocfl
            }

        except Exception as e:
            logger.exception("Error creating bucket", extra={"bucket_name": bucket_name, "error": str(e)})
            return {
                "success": False,
                "error": f"Error creating bucket: {str(e)}"
            }
