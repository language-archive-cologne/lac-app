"""
Unit tests for StorageServiceContext.
"""
from unittest.mock import Mock, MagicMock
from django.test import TestCase

from lacos.storage.services.service_context import StorageServiceContext
from lacos.storage.services.base_storage_service import BaseStorageService


class StorageServiceContextTest(TestCase):
    """Tests for StorageServiceContext."""

    def test_init_creates_context(self):
        """Test that context initializes with provided parameters."""
        mock_s3 = Mock()
        workspace_buckets = ["bucket1", "bucket2"]

        context = StorageServiceContext(
            s3_client=mock_s3,
            workspace_buckets=workspace_buckets,
            ingest_bucket="ingest",
            production_bucket="production",
            is_minio=True,
            endpoint_url="http://localhost:9000"
        )

        self.assertEqual(context.s3_client, mock_s3)
        self.assertEqual(context.workspace_buckets, workspace_buckets)
        self.assertEqual(context.ingest_bucket, "ingest")
        self.assertEqual(context.production_bucket, "production")
        self.assertTrue(context.is_minio)
        self.assertEqual(context.endpoint_url, "http://localhost:9000")
        self.assertIsNotNone(context.folder_cache)

    def test_from_base_service(self):
        """Test factory method creates context from BaseStorageService."""
        mock_service = Mock(spec=BaseStorageService)
        mock_service.s3_client = Mock()
        mock_service.workspace_buckets = ["test"]
        mock_service.ingest_bucket = "ingest"
        mock_service.production_bucket = "prod"
        mock_service.is_minio = False
        mock_service.endpoint_url = None

        context = StorageServiceContext.from_base_service(mock_service)

        self.assertEqual(context.s3_client, mock_service.s3_client)
        self.assertEqual(context.workspace_buckets, ["test"])
        self.assertEqual(context.ingest_bucket, "ingest")
        self.assertEqual(context.production_bucket, "prod")
        self.assertFalse(context.is_minio)
