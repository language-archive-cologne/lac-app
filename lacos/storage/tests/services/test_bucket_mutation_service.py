"""
Unit tests for BucketMutationService.
"""
from unittest.mock import Mock, MagicMock, patch
from django.test import TestCase
from botocore.exceptions import ClientError

from lacos.storage.services.bucket_mutation_service import BucketMutationService
from lacos.storage.services.service_context import StorageServiceContext


class BucketMutationServiceTest(TestCase):
    """Tests for BucketMutationService."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_s3 = Mock()
        self.mock_cache = Mock()
        self.context = StorageServiceContext(
            s3_client=self.mock_s3,
            workspace_buckets=["test"],
            ingest_bucket="ingest",
            production_bucket="production",
            is_minio=True,
        )
        self.context.folder_cache = self.mock_cache
        self.service = BucketMutationService(self.context)

    def test_is_valid_bucket_name(self):
        """Test bucket name validation."""
        self.assertTrue(self.service._is_valid_bucket_name("valid-bucket"))
        self.assertTrue(self.service._is_valid_bucket_name("valid_bucket"))
        self.assertTrue(self.service._is_valid_bucket_name("validbucket123"))
        self.assertFalse(self.service._is_valid_bucket_name(""))
        self.assertFalse(self.service._is_valid_bucket_name("invalid.bucket"))

    def test_split_parent_child(self):
        """Test path splitting."""
        result = self.service._split_parent_child("parent/child/")
        self.assertEqual(result["parent"], "parent/")
        self.assertEqual(result["name"], "child")

        result = self.service._split_parent_child("file.txt")
        self.assertEqual(result["parent"], "")
        self.assertEqual(result["name"], "file.txt")

    def test_rename_file_validation(self):
        """Test file rename validation."""
        # Empty name
        result = self.service.rename_file("bucket", "old.txt", "  ")
        self.assertFalse(result["success"])
        self.assertIn("required", result["error"])

        # Invalid name with slash
        result = self.service.rename_file("bucket", "old.txt", "new/file.txt")
        self.assertFalse(result["success"])
        self.assertIn("must not contain", result["error"])

    def test_rename_file_unchanged(self):
        """Test renaming file to same name."""
        result = self.service.rename_file("bucket", "folder/file.txt", "file.txt")
        self.assertTrue(result["success"])
        self.assertIn("unchanged", result["message"])

    def test_delete_file_success(self):
        """Test successful file deletion."""
        self.mock_s3.delete_object.return_value = {}

        result = self.service.delete_file("bucket", "file.txt")

        self.assertTrue(result["success"])
        self.mock_s3.delete_object.assert_called_once_with(
            Bucket="bucket", Key="file.txt"
        )
        self.mock_cache.delete.assert_called()

    def test_delete_file_error(self):
        """Test file deletion with error."""
        self.mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "delete_object"
        )

        result = self.service.delete_file("bucket", "file.txt")

        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_delete_folder_success(self):
        """Test successful folder deletion."""
        mock_paginator = Mock()
        mock_paginator.paginate.return_value = [
            {"Contents": [{"Key": "folder/file1.txt"}, {"Key": "folder/file2.txt"}]}
        ]
        self.mock_s3.get_paginator.return_value = mock_paginator
        self.mock_s3.delete_objects.return_value = {}

        result = self.service.delete_folder("bucket", "folder/")

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted_count"], 2)
        self.mock_s3.delete_objects.assert_called_once()

    def test_rename_folder_validation(self):
        """Test folder rename validation."""
        # Empty name
        result = self.service.rename_folder("bucket", "old/", "")
        self.assertFalse(result["success"])

        # Name with slash
        result = self.service.rename_folder("bucket", "old/", "new/name")
        self.assertFalse(result["success"])
