"""
Unit tests for BucketMetadataService.
"""
from unittest.mock import Mock, patch
from django.test import TestCase

from lacos.storage.services.bucket_metadata_service import BucketMetadataService
from lacos.storage.services.service_context import StorageServiceContext
from lacos.storage.services.collection_service import CollectionService


class BucketMetadataServiceTest(TestCase):
    """Tests for BucketMetadataService."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_s3 = Mock()
        self.context = StorageServiceContext(
            s3_client=self.mock_s3,
            workspace_buckets=["test"],
            ingest_bucket="ingest",
            production_bucket="production",
            is_minio=True,
        )
        self.mock_collection_service = Mock(spec=CollectionService)
        self.service = BucketMetadataService(self.context, self.mock_collection_service)

    def test_build_blam_metadata_index_empty_list(self):
        """Test that empty folder list returns empty metadata."""
        result = self.service.build_blam_metadata_index("production", [])
        self.assertEqual(result, {})

    def test_build_blam_metadata_index_non_production_bucket(self):
        """Test that non-production bucket returns empty metadata."""
        items = [{"path": "test/", "is_dir": True}]
        result = self.service.build_blam_metadata_index("ingest", items)
        self.assertEqual(result, {})

    @patch('lacos.storage.services.bucket_metadata_service.Collection')
    def test_build_blam_metadata_index_with_collections(self, mock_collection):
        """Test metadata index building with collections."""
        # Mock collection path check
        self.mock_collection_service.is_collection_path.return_value = True

        # Mock database query
        mock_qs = Mock()
        mock_qs.filter.return_value.values_list.return_value = [("col1", 123)]
        mock_collection.objects = mock_qs

        items = [{"path": "col1/", "is_dir": True, "name": "col1"}]
        result = self.service.build_blam_metadata_index("production", items)

        self.assertIn("col1/", result)
        self.assertTrue(result["col1/"]["is_blam_object"])
        self.assertEqual(result["col1/"]["blam_type"], "collection")

    @patch('lacos.storage.services.bucket_metadata_service.Bundle')
    @patch('lacos.storage.services.bucket_metadata_service.Collection')
    def test_build_blam_metadata_index_handles_shared_collection_bundle_names(
        self,
        mock_collection,
        mock_bundle,
    ):
        """Collection and bundle names can overlap; collection path still takes precedence."""
        self.mock_collection_service.is_collection_path.side_effect = (
            lambda path: path == "same/same/"
        )

        mock_collection_qs = Mock()
        mock_collection_qs.filter.return_value.values_list.return_value = [("same", 101)]
        mock_collection.objects = mock_collection_qs

        mock_bundle_qs = Mock()
        mock_bundle_qs.filter.return_value.values_list.return_value = [("same", 202)]
        mock_bundle.objects = mock_bundle_qs

        items = [
            {"path": "same/same/", "is_dir": True, "name": "same"},
            {"path": "other/same/", "is_dir": True, "name": "same"},
        ]

        result = self.service.build_blam_metadata_index("production", items)

        self.assertEqual(result["same/same/"]["blam_type"], "collection")
        self.assertEqual(result["same/same/"]["blam_id"], "101")
        self.assertEqual(result["other/same/"]["blam_type"], "bundle")
        self.assertEqual(result["other/same/"]["blam_id"], "202")

    def test_is_blam_object_non_production(self):
        """Test is_blam_object returns False for non-production bucket."""
        result = self.service.is_blam_object("ingest", "test/path")
        self.assertFalse(result["is_blam_object"])
        self.assertIsNone(result["blam_type"])
        self.assertIsNone(result["blam_id"])

    def test_enrich_folder_items_empty(self):
        """Test enriching empty items list."""
        result = self.service.enrich_folder_items("production", [])
        self.assertEqual(result, [])

    def test_enrich_folder_items_with_files(self):
        """Test enriching items preserves file entries."""
        items = [
            {"path": "file.txt", "is_dir": False, "name": "file.txt"},
            {"path": "folder/", "is_dir": True, "name": "folder"}
        ]
        result = self.service.enrich_folder_items("ingest", items)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0]["is_dir"])
        self.assertTrue(result[1]["is_dir"])
