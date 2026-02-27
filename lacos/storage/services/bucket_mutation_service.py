"""
Bucket mutation service for storage operations.

This service handles rename, delete, and copy/move operations for buckets,
folders, and files. It centralizes validation and audit logging for mutations.
"""
import logging
from typing import Dict, Any
from botocore.exceptions import ClientError

from .service_context import StorageServiceContext

logger = logging.getLogger(__name__)


class BucketMutationService:
    """
    Service for mutating bucket contents (rename, delete, copy/move).

    Handles validation, S3 operations, and cache invalidation for all
    mutation operations on buckets, folders, and files.
    """

    def __init__(self, context: StorageServiceContext):
        """
        Initialize the mutation service.

        Args:
            context: Shared service context
        """
        self.context = context

    def _is_valid_bucket_name(self, bucket_name: str) -> bool:
        """
        Validate bucket name format.

        Args:
            bucket_name: Name to validate

        Returns:
            bool: True if valid
        """
        if not bucket_name:
            return False
        return bucket_name.replace('-', '').replace('_', '').isalnum()

    def _split_parent_child(self, path: str) -> Dict[str, str]:
        """
        Split a path into parent and child components.

        Args:
            path: Full path (e.g., "parent/child/")

        Returns:
            Dict with 'parent' and 'name' keys
        """
        normalized = path.rstrip('/')
        if '/' in normalized:
            parts = normalized.rsplit('/', 1)
            return {'parent': parts[0] + '/', 'name': parts[1]}
        else:
            return {'parent': '', 'name': normalized}

    def rename_bucket(self, current_bucket: str, new_bucket: str) -> Dict[str, Any]:
        """
        Rename a bucket by copying all objects to a new bucket and deleting the old one.

        Args:
            current_bucket: Current bucket name
            new_bucket: New bucket name

        Returns:
            Dict with success status, message, and metadata
        """
        try:
            current_bucket = current_bucket.strip()
            new_bucket = new_bucket.strip()

            if not current_bucket:
                return {"success": False, "error": "Current bucket name is required"}

            if not new_bucket:
                return {"success": False, "error": "New bucket name is required"}

            if current_bucket == new_bucket:
                return {"success": False, "error": "New bucket name must be different"}

            if not self._is_valid_bucket_name(new_bucket):
                return {
                    "success": False,
                    "error": "Invalid bucket name. Use only letters, numbers, hyphens, and underscores.",
                }

            # Check bucket accessibility (will need to be provided by caller or context)
            # For now, assume validation is done at a higher level

            # Copy all objects
            paginator = self.context.s3_client.get_paginator("list_objects_v2")
            copied_objects = 0

            for page in paginator.paginate(Bucket=current_bucket):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    self.context.s3_client.copy_object(
                        Bucket=new_bucket,
                        CopySource={"Bucket": current_bucket, "Key": key},
                        Key=key,
                    )
                    self.context.s3_client.delete_object(Bucket=current_bucket, Key=key)
                    copied_objects += 1

            # Delete the now-empty bucket
            self.context.s3_client.delete_bucket(Bucket=current_bucket)

            # Invalidate cache for both buckets
            self.context.folder_cache.delete(current_bucket, None)
            self.context.folder_cache.delete(new_bucket, None)

            message = f"Bucket '{current_bucket}' renamed to '{new_bucket}'"
            return {
                "success": True,
                "message": message,
                "objects_moved": copied_objects,
                "bucket_name": new_bucket,
            }

        except ClientError as e:
            logger.error(
                "Error renaming bucket",
                extra={"current_bucket": current_bucket, "new_bucket": new_bucket, "error": str(e)},
            )
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception("Unexpected error renaming bucket", extra={"current_bucket": current_bucket})
            return {"success": False, "error": str(e)}

    def rename_folder(
        self, bucket_name: str, old_path: str, new_name: str
    ) -> Dict[str, Any]:
        """
        Rename a folder within a bucket by copying to a new prefix and deleting the old.

        Args:
            bucket_name: Bucket containing the folder
            old_path: Current folder path
            new_name: New folder name (not full path)

        Returns:
            Dict with success status, message, and metadata
        """
        try:
            new_name = new_name.strip()
            if not new_name:
                return {"success": False, "error": "New folder name is required"}

            if "/" in new_name:
                return {"success": False, "error": "Folder name must not contain '/'"}

            old_prefix = old_path if old_path.endswith("/") else f"{old_path}/"
            parent = self._split_parent_child(old_prefix)
            if not parent["name"]:
                return {"success": False, "error": "Invalid folder path"}

            if parent["name"] == new_name:
                return {"success": True, "message": "Folder name unchanged"}

            new_prefix = f"{parent['parent']}{new_name}/"

            # Ensure target prefix does not already exist
            existing = self.context.s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=new_prefix, MaxKeys=1
            )
            if existing.get("KeyCount", 0) > 0:
                return {"success": False, "error": f"Folder '{new_name}' already exists"}

            # Copy all objects with the old prefix
            paginator = self.context.s3_client.get_paginator("list_objects_v2")
            moved = 0

            for page in paginator.paginate(Bucket=bucket_name, Prefix=old_prefix):
                for obj in page.get("Contents", []):
                    old_key = obj["Key"]
                    suffix = old_key[len(old_prefix) :]
                    new_key = f"{new_prefix}{suffix}" if suffix else new_prefix

                    self.context.s3_client.copy_object(
                        Bucket=bucket_name,
                        CopySource={"Bucket": bucket_name, "Key": old_key},
                        Key=new_key,
                    )
                    self.context.s3_client.delete_object(Bucket=bucket_name, Key=old_key)
                    moved += 1

            # Invalidate cache for affected paths
            self.context.folder_cache.delete(bucket_name, parent["parent"])
            self.context.folder_cache.delete(bucket_name, old_prefix)
            self.context.folder_cache.delete(bucket_name, new_prefix)

            if moved == 0:
                response = {
                    "success": True,
                    "message": "Folder was empty",
                    "folder_path": new_prefix,
                }
            else:
                response = {
                    "success": True,
                    "message": f"Folder renamed to '{new_name}'",
                    "folder_path": new_prefix,
                    "objects_moved": moved,
                }

            return response

        except ClientError as e:
            logger.error("Error renaming folder", extra={"old_path": old_path, "new_name": new_name, "error": str(e)})
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception("Unexpected error renaming folder", extra={"old_path": old_path})
            return {"success": False, "error": str(e)}

    def rename_file(
        self, bucket_name: str, file_path: str, new_name: str
    ) -> Dict[str, Any]:
        """
        Rename a single file within a bucket.

        Args:
            bucket_name: Bucket containing the file
            file_path: Current file path
            new_name: New file name (not full path)

        Returns:
            Dict with success status, message, and metadata
        """
        try:
            new_name = new_name.strip()
            if not new_name:
                return {"success": False, "error": "New file name is required"}

            if "/" in new_name:
                return {"success": False, "error": "File name must not contain '/'"}

            parent = self._split_parent_child(file_path)
            if not parent["name"]:
                return {"success": False, "error": "Invalid file path"}

            if parent["name"] == new_name:
                return {"success": True, "message": "File name unchanged"}

            new_key = f"{parent['parent']}{new_name}"

            # Ensure target does not already exist
            try:
                self.context.s3_client.head_object(Bucket=bucket_name, Key=new_key)
                return {"success": False, "error": f"File '{new_name}' already exists"}
            except ClientError as head_error:
                if head_error.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                    raise

            # Copy and delete
            self.context.s3_client.copy_object(
                Bucket=bucket_name,
                CopySource={"Bucket": bucket_name, "Key": file_path},
                Key=new_key,
            )
            self.context.s3_client.delete_object(Bucket=bucket_name, Key=file_path)

            # Invalidate parent folder cache
            self.context.folder_cache.delete(bucket_name, parent["parent"])

            response = {
                "success": True,
                "message": f"File renamed to '{new_name}'",
                "file_path": new_key,
            }
            return response

        except ClientError as e:
            logger.error("Error renaming file", extra={"file_path": file_path, "new_name": new_name, "error": str(e)})
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception("Unexpected error renaming file", extra={"file_path": file_path})
            return {"success": False, "error": str(e)}

    def delete_folder(self, bucket_name: str, folder_path: str) -> Dict[str, Any]:
        """
        Delete a folder and all its contents from the specified bucket.

        Args:
            bucket_name: The name of the bucket
            folder_path: Path to the folder to delete

        Returns:
            Dict with success status and message
        """
        try:
            prefix = folder_path if folder_path.endswith("/") else f"{folder_path}/"
            paginator = self.context.s3_client.get_paginator("list_objects_v2")
            deleted = 0

            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                objects_to_delete = [
                    {"Key": obj["Key"]} for obj in page.get("Contents", [])
                ]
                if objects_to_delete:
                    self.context.s3_client.delete_objects(
                        Bucket=bucket_name, Delete={"Objects": objects_to_delete}
                    )
                    deleted += len(objects_to_delete)

            # Invalidate cache
            parent = self._split_parent_child(folder_path)
            self.context.folder_cache.delete(bucket_name, parent["parent"])
            self.context.folder_cache.delete(bucket_name, folder_path)

            return {
                "success": True,
                "message": f"Deleted folder and {deleted} objects",
                "deleted_count": deleted,
            }

        except ClientError as e:
            logger.error("Error deleting folder", extra={"folder_path": folder_path, "error": str(e)})
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception("Unexpected error deleting folder", extra={"folder_path": folder_path})
            return {"success": False, "error": str(e)}

    def delete_file(self, bucket_name: str, file_path: str) -> Dict[str, Any]:
        """
        Delete a single file from the specified bucket.

        Args:
            bucket_name: The name of the bucket
            file_path: Path to the file to delete

        Returns:
            Dict with success status and message
        """
        try:
            self.context.s3_client.delete_object(Bucket=bucket_name, Key=file_path)

            # Invalidate parent folder cache
            parent = self._split_parent_child(file_path)
            self.context.folder_cache.delete(bucket_name, parent["parent"])

            return {"success": True, "message": f"Deleted file '{file_path}'"}

        except ClientError as e:
            logger.error("Error deleting file", extra={"file_path": file_path, "error": str(e)})
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.exception("Unexpected error deleting file", extra={"file_path": file_path})
            return {"success": False, "error": str(e)}
