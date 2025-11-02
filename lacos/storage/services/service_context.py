"""
Service context for storage operations.

This module provides a shared context object that holds common dependencies
(S3 client, bucket names, cache services) to avoid duplicate initialization
and ensure consistent configuration across all storage service helpers.
"""
import logging
from typing import Optional
from django.conf import settings
import boto3

from .folder_cache_service import FolderStructureCacheService

logger = logging.getLogger(__name__)


class StorageServiceContext:
    """
    Shared context for storage service operations.

    Holds S3 client, bucket configuration, and cache services that are
    shared across all storage helper services. Built once and reused.
    """

    def __init__(
        self,
        s3_client,
        workspace_buckets: list,
        ingest_bucket: str,
        production_bucket: str,
        is_minio: bool,
        endpoint_url: Optional[str] = None,
        folder_cache: Optional[FolderStructureCacheService] = None,
    ):
        """
        Initialize the service context.

        Args:
            s3_client: Boto3 S3 client instance
            workspace_buckets: List of accessible workspace bucket names
            ingest_bucket: Legacy ingest bucket name
            production_bucket: Legacy production bucket name
            is_minio: Whether using MinIO (vs AWS S3)
            endpoint_url: MinIO/S3 endpoint URL
            folder_cache: Optional folder cache service instance
        """
        self.s3_client = s3_client
        self.workspace_buckets = workspace_buckets
        self.ingest_bucket = ingest_bucket
        self.production_bucket = production_bucket
        self.is_minio = is_minio
        self.endpoint_url = endpoint_url

        # Initialize or use provided cache service
        self.folder_cache = folder_cache or FolderStructureCacheService()

        # Dashboard pagination settings
        self.dashboard_pagination_enabled = getattr(
            settings, "STORAGE_DASHBOARD_PAGINATION_ENABLED", True
        )
        self.dashboard_page_size = getattr(
            settings, "STORAGE_DASHBOARD_PAGE_SIZE", 200
        )

        logger.debug(
            f"StorageServiceContext initialized with {len(workspace_buckets)} workspace buckets"
        )

    @classmethod
    def from_base_service(cls, base_service):
        """
        Create a context from an existing BaseStorageService instance.

        Args:
            base_service: An initialized BaseStorageService instance

        Returns:
            StorageServiceContext: New context built from service state
        """
        # Get or create folder cache
        folder_cache = getattr(
            base_service, 'folder_cache', FolderStructureCacheService()
        )

        return cls(
            s3_client=base_service.s3_client,
            workspace_buckets=base_service.workspace_buckets,
            ingest_bucket=base_service.ingest_bucket,
            production_bucket=base_service.production_bucket,
            is_minio=base_service.is_minio,
            endpoint_url=base_service.endpoint_url,
            folder_cache=folder_cache,
        )
