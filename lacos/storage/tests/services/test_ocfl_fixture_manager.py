import pytest
import json
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, mock_open
from django.test import TestCase

from lacos.storage.services.ocfl_fixture_manager import (
    OCFLFixtureManager, PreservationMetadata, FixtureBackup
)


class TestOCFLFixtureManager(TestCase):
    """Test cases for OCFLFixtureManager"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_bucket_service = Mock()
        self.temp_dir = tempfile.mkdtemp()
        self.fixture_manager = OCFLFixtureManager(
            self.mock_bucket_service,
            temp_storage_path=self.temp_dir
        )

    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_extract_existing_metadata_complete(self):
        """Test extracting complete metadata from folder"""
        # Mock folder contents
        contents = [
            {"name": "acl.json", "is_dir": False, "size": 256},
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "description.xml", "is_dir": False, "size": 512},
            {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
            {"name": "data", "is_dir": True},
            {"name": "manifest.json", "is_dir": False, "size": 128}
        ]

        # Mock S3 responses for file content
        def mock_get_object(Bucket, Key):
            mock_response = Mock()
            if Key.endswith("acl.json"):
                mock_response['Body'].read.return_value = b'{"permissions": ["read"]}'
            elif Key.endswith("metadata.xml"):
                mock_response['Body'].read.return_value = b'<metadata>test</metadata>'
            elif Key.endswith("description.xml"):
                mock_response['Body'].read.return_value = b'<description>test desc</description>'
            elif Key.endswith("manifest.json"):
                mock_response['Body'].read.return_value = b'{"files": []}'
            return mock_response

        self.mock_bucket_service.list_bucket_contents.return_value = contents
        self.mock_bucket_service.s3_client.get_object.side_effect = mock_get_object

        metadata = self.fixture_manager.extract_existing_metadata("test-bucket", "test/folder")

        # Verify extracted data
        self.assertIsNotNone(metadata.acl_data)
        self.assertEqual(metadata.acl_data["permissions"], ["read"])
        self.assertEqual(len(metadata.xml_files), 2)
        self.assertIn("metadata.xml", metadata.xml_files)
        self.assertIn("description.xml", metadata.xml_files)
        self.assertEqual(metadata.xml_files["metadata.xml"], "<metadata>test</metadata>")
        self.assertEqual(len(metadata.ocfl_markers), 1)
        self.assertIn("0=ocfl_object_1.0", metadata.ocfl_markers)
        self.assertIn("manifest.json", metadata.custom_metadata)

    def test_extract_existing_metadata_empty_folder(self):
        """Test extracting metadata from empty folder"""
        self.mock_bucket_service.list_bucket_contents.return_value = []

        metadata = self.fixture_manager.extract_existing_metadata("test-bucket", "empty/folder")

        self.assertIsNone(metadata.acl_data)
        self.assertEqual(len(metadata.xml_files), 0)
        self.assertEqual(len(metadata.ocfl_markers), 0)
        self.assertEqual(len(metadata.custom_metadata), 0)

    @patch('lacos.storage.services.ocfl_fixture_manager.logger')
    def test_extract_existing_metadata_s3_error(self, mock_logger):
        """Test handling S3 errors during metadata extraction"""
        contents = [{"name": "acl.json", "is_dir": False, "size": 256}]
        self.mock_bucket_service.list_bucket_contents.return_value = contents
        self.mock_bucket_service.s3_client.get_object.side_effect = Exception("S3 access error")

        metadata = self.fixture_manager.extract_existing_metadata("test-bucket", "test/folder")

        self.assertIn("extraction_error", metadata.custom_metadata)
        mock_logger.warning.assert_called()

    def test_apply_fixtures_success(self):
        """Test successfully applying fixtures to OCFL structure"""
        # Create test metadata
        metadata = PreservationMetadata()
        metadata.acl_data = {"permissions": ["read", "write"]}
        metadata.xml_files = {
            "metadata.xml": "<metadata>test</metadata>",
            "description.xml": "<description>test desc</description>"
        }
        metadata.ocfl_markers = ["0=ocfl_object_1.0"]
        metadata.custom_metadata = {"readme.txt": "Test content"}

        # Mock successful S3 operations
        self.mock_bucket_service.s3_client.put_object.return_value = {}

        result = self.fixture_manager.apply_fixtures(
            "test-bucket", "test/ocfl/folder", metadata
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["applied_fixtures"]), 5)  # ACL + 2 XML + 1 marker + 1 custom
        self.assertIn("acl.json", result["applied_fixtures"])
        self.assertIn("metadata.xml", result["applied_fixtures"])
        self.assertIn("0=ocfl_object_1.0", result["applied_fixtures"])

        # Verify S3 put_object calls
        expected_calls = 5  # ACL + 2 XML + 1 marker + 1 custom + 1 directory marker
        self.assertGreaterEqual(self.mock_bucket_service.s3_client.put_object.call_count, expected_calls)

    def test_apply_fixtures_partial_failure(self):
        """Test applying fixtures with some failures"""
        metadata = PreservationMetadata()
        metadata.acl_data = {"permissions": ["read"]}
        metadata.xml_files = {"metadata.xml": "<metadata>test</metadata>"}

        # Mock S3 operations with one failure
        def mock_put_object(**kwargs):
            if "acl.json" in kwargs.get("Key", ""):
                raise Exception("Access denied")
            return {}

        self.mock_bucket_service.s3_client.put_object.side_effect = mock_put_object

        result = self.fixture_manager.apply_fixtures(
            "test-bucket", "test/ocfl/folder", metadata
        )

        self.assertFalse(result["success"])
        self.assertIn("metadata.xml", result["applied_fixtures"])
        self.assertGreater(len(result["errors"]), 0)
        self.assertIn("Failed to apply ACL data", result["errors"][0])

    def test_create_fixture_backup(self):
        """Test creating backup of folder fixtures"""
        # Mock folder contents
        contents = [
            {"name": "acl.json", "is_dir": False, "size": 256},
            {"name": "metadata.xml", "is_dir": False, "size": 1024}
        ]

        # Mock S3 get_object for metadata extraction
        def mock_get_object(Bucket, Key):
            mock_response = Mock()
            if Key.endswith("acl.json"):
                mock_response['Body'].read.return_value = b'{"permissions": ["read"]}'
            elif Key.endswith("metadata.xml"):
                mock_response['Body'].read.return_value = b'<metadata>test</metadata>'
            return mock_response

        self.mock_bucket_service.list_bucket_contents.return_value = contents
        self.mock_bucket_service.s3_client.get_object.side_effect = mock_get_object
        self.mock_bucket_service._download_directory.return_value = None

        backup_id = self.fixture_manager.create_fixture_backup("test-bucket", "test/folder")

        self.assertIsNotNone(backup_id)
        self.assertIn(backup_id, self.fixture_manager.active_backups)

        # Verify backup structure
        backup = self.fixture_manager.active_backups[backup_id]
        self.assertEqual(backup.original_path, "test/folder")
        self.assertIsNotNone(backup.metadata.acl_data)

        # Verify backup files exist
        backup_metadata_file = os.path.join(backup.backup_location, "backup_metadata.json")
        self.assertTrue(os.path.exists(backup_metadata_file))

    @patch('lacos.storage.services.ocfl_fixture_manager.logger')
    def test_create_fixture_backup_download_error(self, mock_logger):
        """Test backup creation with download error"""
        self.mock_bucket_service.list_bucket_contents.return_value = []
        self.mock_bucket_service._download_directory.side_effect = Exception("Download failed")

        with self.assertRaises(Exception):
            self.fixture_manager.create_fixture_backup("test-bucket", "test/folder")

        mock_logger.error.assert_called()

    def test_restore_from_backup(self):
        """Test restoring folder from backup"""
        # Create a mock backup
        backup_id = "test_backup_123"
        backup_location = os.path.join(self.temp_dir, "backup_test")
        os.makedirs(backup_location, exist_ok=True)

        # Create backup files
        test_file = os.path.join(backup_location, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        metadata = PreservationMetadata()
        backup = FixtureBackup(
            backup_id=backup_id,
            original_path="test/folder",
            backup_location=backup_location,
            metadata=metadata
        )

        self.fixture_manager.active_backups[backup_id] = backup

        # Mock successful upload
        self.mock_bucket_service._upload_directory.return_value = {
            "success": True,
            "total_files": 1
        }

        result = self.fixture_manager.restore_from_backup(backup_id, "test-bucket")

        self.assertTrue(result["success"])
        self.assertEqual(result["files_restored"], 1)
        self.mock_bucket_service._upload_directory.assert_called_once()

    def test_restore_from_backup_not_found(self):
        """Test restoring from non-existent backup"""
        result = self.fixture_manager.restore_from_backup("nonexistent", "test-bucket")

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    def test_restore_from_backup_upload_failure(self):
        """Test restore with upload failure"""
        backup_id = "test_backup_123"
        metadata = PreservationMetadata()
        backup = FixtureBackup(
            backup_id=backup_id,
            original_path="test/folder",
            backup_location="/tmp/backup",
            metadata=metadata
        )

        self.fixture_manager.active_backups[backup_id] = backup

        # Mock upload failure
        self.mock_bucket_service._upload_directory.return_value = {
            "success": False,
            "error": "Upload failed"
        }

        result = self.fixture_manager.restore_from_backup(backup_id, "test-bucket")

        self.assertFalse(result["success"])
        self.assertIn("Failed to upload backup", result["error"])

    def test_cleanup_backup(self):
        """Test cleaning up backup files"""
        # Create a mock backup with actual files
        backup_id = "test_backup_123"
        backup_location = os.path.join(self.temp_dir, "backup_test")
        os.makedirs(backup_location, exist_ok=True)

        test_file = os.path.join(backup_location, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        metadata = PreservationMetadata()
        backup = FixtureBackup(
            backup_id=backup_id,
            original_path="test/folder",
            backup_location=backup_location,
            metadata=metadata
        )

        self.fixture_manager.active_backups[backup_id] = backup

        result = self.fixture_manager.cleanup_backup(backup_id)

        self.assertTrue(result)
        self.assertNotIn(backup_id, self.fixture_manager.active_backups)
        self.assertFalse(os.path.exists(backup_location))

    def test_cleanup_backup_not_found(self):
        """Test cleaning up non-existent backup"""
        result = self.fixture_manager.cleanup_backup("nonexistent")

        self.assertFalse(result)

    def test_list_active_backups(self):
        """Test listing active backups"""
        # Create mock backups
        for i in range(3):
            backup_id = f"backup_{i}"
            metadata = PreservationMetadata()
            metadata.acl_data = {"test": "data"}
            metadata.xml_files = {"test.xml": "content"}

            backup = FixtureBackup(
                backup_id=backup_id,
                original_path=f"test/folder{i}",
                backup_location=f"/tmp/backup{i}",
                metadata=metadata
            )

            self.fixture_manager.active_backups[backup_id] = backup

        backups = self.fixture_manager.list_active_backups()

        self.assertEqual(len(backups), 3)

        for backup_info in backups:
            self.assertIn("backup_id", backup_info)
            self.assertIn("original_path", backup_info)
            self.assertIn("creation_timestamp", backup_info)
            self.assertTrue(backup_info["has_acl"])
            self.assertEqual(backup_info["xml_files_count"], 1)

    def test_ensure_directory_exists(self):
        """Test ensuring directory exists in S3"""
        self.fixture_manager._ensure_directory_exists("test-bucket", "test/path/metadata")

        self.mock_bucket_service.s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="test/path/metadata/",
            Body=""
        )

    def test_apply_acl_data(self):
        """Test applying ACL data specifically"""
        acl_data = {"permissions": ["read", "write"]}
        results = {"applied_fixtures": [], "errors": []}

        self.mock_bucket_service.s3_client.put_object.return_value = {}

        self.fixture_manager._apply_acl_data(
            "test-bucket", "test/metadata", acl_data, results
        )

        self.assertIn("acl.json", results["applied_fixtures"])
        self.assertEqual(len(results["errors"]), 0)

        # Verify the call
        call_args = self.mock_bucket_service.s3_client.put_object.call_args
        self.assertEqual(call_args[1]["Key"], "test/metadata/acl.json")
        self.assertIn("permissions", call_args[1]["Body"])

    def test_apply_xml_files(self):
        """Test applying XML files specifically"""
        xml_files = {
            "metadata.xml": "<metadata>test</metadata>",
            "description.xml": "<description>desc</description>"
        }
        results = {"applied_fixtures": [], "errors": []}

        self.mock_bucket_service.s3_client.put_object.return_value = {}

        self.fixture_manager._apply_xml_files(
            "test-bucket", "test/metadata", xml_files, results
        )

        self.assertEqual(len(results["applied_fixtures"]), 2)
        self.assertIn("metadata.xml", results["applied_fixtures"])
        self.assertIn("description.xml", results["applied_fixtures"])

    def test_apply_xml_files_with_error(self):
        """Test applying XML files with S3 error"""
        xml_files = {"metadata.xml": "<metadata>test</metadata>"}
        results = {"applied_fixtures": [], "errors": []}

        self.mock_bucket_service.s3_client.put_object.side_effect = Exception("S3 error")

        self.fixture_manager._apply_xml_files(
            "test-bucket", "test/metadata", xml_files, results
        )

        self.assertEqual(len(results["applied_fixtures"]), 0)
        self.assertEqual(len(results["errors"]), 1)
        self.assertIn("Failed to apply XML file", results["errors"][0])

    def test_load_backup_from_file(self):
        """Test loading backup information from file"""
        backup_id = "test_backup_123"
        backup_dir = os.path.join(self.temp_dir, "ocfl_backups", backup_id)
        os.makedirs(backup_dir, exist_ok=True)

        # Create backup metadata file
        backup_data = {
            "backup_id": backup_id,
            "original_path": "test/folder",
            "backup_location": backup_dir,
            "creation_timestamp": "2024-01-01T00:00:00",
            "metadata": {
                "acl_data": {"permissions": ["read"]},
                "xml_files": {"test.xml": "content"},
                "ocfl_markers": ["0=ocfl_object_1.0"],
                "custom_metadata": {},
                "directory_structure": {},
                "extraction_timestamp": "2024-01-01T00:00:00"
            }
        }

        backup_file = os.path.join(backup_dir, "backup_metadata.json")
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f)

        # Test loading
        self.fixture_manager._load_backup_from_file(backup_id)

        self.assertIn(backup_id, self.fixture_manager.active_backups)
        backup = self.fixture_manager.active_backups[backup_id]
        self.assertEqual(backup.original_path, "test/folder")
        self.assertEqual(backup.metadata.acl_data["permissions"], ["read"])

    def test_extract_directory_structure(self):
        """Test extracting directory structure"""
        contents = [
            {"name": "dir1", "is_dir": True},
            {"name": "dir2", "is_dir": True},
            {"name": "file1.txt", "is_dir": False, "size": 100, "last_modified": "2024-01-01"},
            {"name": "file2.xml", "is_dir": False, "size": 200, "last_modified": "2024-01-02"}
        ]

        metadata = PreservationMetadata()
        self.fixture_manager._extract_directory_structure(contents, metadata)

        structure = metadata.directory_structure
        self.assertEqual(len(structure["directories"]), 2)
        self.assertEqual(len(structure["files"]), 2)
        self.assertEqual(structure["total_items"], 4)
        self.assertIn("dir1", structure["directories"])
        self.assertIn("dir2", structure["directories"])

        # Check file details
        file_names = [f["name"] for f in structure["files"]]
        self.assertIn("file1.txt", file_names)
        self.assertIn("file2.xml", file_names)
