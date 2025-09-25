import pytest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, call, mock_open, MagicMock
from django.test import TestCase

from lacos.storage.services.ocfl_service import OCFLService


class TestOCFLServiceEnhanced(TestCase):
    """Test cases for enhanced OCFLService with in-place conversion"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_bucket_service = Mock()
        self.ocfl_service = OCFLService(self.mock_bucket_service)

    def test_analyze_folder_structure_complete_ocfl(self):
        """Test analyzing a complete OCFL structure"""
        contents = [
            {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
            {"name": "v1", "is_dir": True},
            {"name": "content", "is_dir": True},
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "acl.json", "is_dir": False, "size": 256},
            {"name": "Resources", "is_dir": True}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.ocfl_service.analyze_folder_structure("test-bucket", "test/folder")

        self.assertTrue(result["success"])
        self.assertEqual(result["folder_path"], "test/folder")

        structure = result["structure_analysis"]
        self.assertTrue(structure["is_ocfl_compliant"])
        self.assertTrue(structure["has_ocfl_marker"])
        self.assertTrue(structure["has_version_directory"])
        self.assertTrue(structure["has_content_directory"])
        self.assertTrue(structure["has_metadata_files"])
        self.assertTrue(structure["has_acl_file"])
        self.assertTrue(structure["has_resources_directory"])
        self.assertEqual(structure["total_files"], 3)

    def test_analyze_folder_structure_partial_ocfl(self):
        """Test analyzing a partial OCFL structure"""
        contents = [
            {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "Resources", "is_dir": True}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.ocfl_service.analyze_folder_structure("test-bucket", "test/folder")

        structure = result["structure_analysis"]
        self.assertFalse(structure["is_ocfl_compliant"])
        self.assertTrue(structure["partial_ocfl"])
        self.assertTrue(structure["has_ocfl_marker"])
        self.assertFalse(structure["has_version_directory"])

    def test_analyze_folder_structure_legacy(self):
        """Test analyzing a legacy structure"""
        contents = [
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "description.xml", "is_dir": False, "size": 512},
            {"name": "Resources", "is_dir": True},
            {"name": "acl.json", "is_dir": False, "size": 256}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.ocfl_service.analyze_folder_structure("test-bucket", "test/folder")

        structure = result["structure_analysis"]
        self.assertFalse(structure["is_ocfl_compliant"])
        self.assertFalse(structure["partial_ocfl"])
        self.assertFalse(structure["has_ocfl_marker"])
        self.assertTrue(structure["has_metadata_files"])
        self.assertTrue(structure["has_resources_directory"])
        self.assertTrue(structure["has_acl_file"])
        self.assertEqual(len(structure["xml_files"]), 2)

    def test_analyze_folder_structure_empty(self):
        """Test analyzing an empty folder"""
        self.mock_bucket_service.list_bucket_contents.return_value = []

        result = self.ocfl_service.analyze_folder_structure("test-bucket", "test/folder")

        self.assertFalse(result["success"])
        self.assertIn("not found or empty", result["error"])

    def test_create_conversion_plan_already_compliant(self):
        """Test creating conversion plan for already compliant folder"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": True,
                "total_files": 10,
                "total_size": 1024
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertFalse(plan["feasible"])
        self.assertEqual(plan["conversion_type"], "none_needed")
        self.assertIn("Already OCFL compliant", plan["risks"])

    def test_create_conversion_plan_partial_ocfl(self):
        """Test creating conversion plan for partial OCFL"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "partial_ocfl": True,
                "has_acl_file": True,
                "xml_files": ["metadata.xml"],
                "total_files": 10,
                "total_size": 1024
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["conversion_type"], "complete_partial")
        self.assertIn("Complete existing OCFL structure", plan["steps"][0])
        self.assertIn("acl.json", plan["preserve_items"])
        self.assertIn("metadata.xml", plan["preserve_items"])

    def test_create_conversion_plan_structured_legacy(self):
        """Test creating conversion plan for structured legacy"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "partial_ocfl": False,
                "has_metadata_files": True,
                "has_resources_directory": True,
                "has_acl_file": False,
                "xml_files": ["metadata.xml", "description.xml"],
                "total_files": 50,
                "total_size": 1024
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["conversion_type"], "structured_to_ocfl")
        self.assertIn("Create OCFL markers", plan["steps"][0])
        self.assertEqual(len(plan["preserve_items"]), 2)

    def test_create_conversion_plan_flat_legacy(self):
        """Test creating conversion plan for flat legacy structure"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "partial_ocfl": False,
                "has_metadata_files": True,
                "has_resources_directory": False,
                "xml_files": ["metadata.xml"],
                "total_files": 100,
                "total_size": 1024
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertTrue(plan["feasible"])
        self.assertEqual(plan["conversion_type"], "flat_to_ocfl")
        self.assertIn("Create OCFL structure", plan["steps"][0])

    def test_create_conversion_plan_unknown_structure(self):
        """Test creating conversion plan for unknown structure"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "partial_ocfl": False,
                "has_metadata_files": False,
                "has_resources_directory": False,
                "xml_files": [],
                "total_files": 10,
                "total_size": 1024
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertFalse(plan["feasible"])
        self.assertEqual(plan["conversion_type"], "unknown_structure")
        self.assertIn("Unknown structure type", plan["risks"])

    def test_create_conversion_plan_large_folder_risks(self):
        """Test conversion plan risk assessment for large folders"""
        analysis_result = {
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "has_metadata_files": True,
                "has_resources_directory": True,
                "xml_files": ["metadata.xml"],
                "total_files": 2000,  # Large number of files
                "total_size": 2 * 1024 * 1024 * 1024  # 2GB
            }
        }

        plan = self.ocfl_service.create_conversion_plan(analysis_result)

        self.assertTrue(plan["feasible"])
        self.assertIn("Large number of files", plan["risks"][0])
        self.assertIn("Large folder size", plan["risks"][1])
        self.assertEqual(plan["estimated_time"], "15-30 minutes")

    @patch('lacos.storage.services.ocfl_service.tempfile.TemporaryDirectory')
    @patch('lacos.storage.services.ocfl_service.uuid.uuid4')
    def test_convert_bundle_to_ocfl_success(self, mock_uuid, mock_temp_dir):
        """Test successful in-place conversion"""
        # Mock UUID for temp folder naming
        mock_uuid.return_value.hex = "abcd1234"

        # Mock temporary directory context manager
        temp_dir_instance = MagicMock()
        temp_dir_instance.__enter__.return_value = "/tmp/test_workspace"
        temp_dir_instance.__exit__.return_value = None
        mock_temp_dir.return_value = temp_dir_instance

        # Mock analysis and conversion plan
        analysis_result = {
            "success": True,
            "structure_analysis": {
                "is_ocfl_compliant": False,
                "has_metadata_files": True,
                "has_resources_directory": True,
                "xml_files": ["metadata.xml"],
                "total_files": 10,
                "total_size": 1024
            }
        }

        conversion_plan = {
            "feasible": True,
            "conversion_type": "structured_to_ocfl",
            "preserve_items": ["metadata.xml"]
        }

        # Mock the methods used in convert_bundle_to_ocfl
        self.ocfl_service.analyze_folder_structure = Mock(return_value=analysis_result)
        self.ocfl_service.create_conversion_plan = Mock(return_value=conversion_plan)
        self.ocfl_service._perform_atomic_conversion = Mock(return_value={
            "success": True,
            "message": "Conversion successful",
            "conversion_type": "structured_to_ocfl",
            "files_processed": 10,
            "preserved_items": ["metadata.xml"]
        })

        result = self.ocfl_service.convert_bundle_to_ocfl("test-bucket", "test/folder")

        self.assertTrue(result["success"])
        self.assertEqual(result["conversion_type"], "structured_to_ocfl")
        self.assertEqual(result["files_processed"], 10)

    def test_convert_bundle_to_ocfl_already_compliant(self):
        """Test in-place conversion of already compliant folder"""
        analysis_result = {
            "success": True,
            "structure_analysis": {
                "is_ocfl_compliant": True
            }
        }

        self.ocfl_service.analyze_folder_structure = Mock(return_value=analysis_result)

        result = self.ocfl_service.convert_bundle_to_ocfl("test-bucket", "test/folder")

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "Bundle is already OCFL compliant")
        self.assertFalse(result["needs_conversion"])

    def test_convert_bundle_to_ocfl_analysis_failure(self):
        """Test in-place conversion when analysis fails"""
        analysis_result = {
            "success": False,
            "error": "Failed to analyze folder"
        }

        self.ocfl_service.analyze_folder_structure = Mock(return_value=analysis_result)

        result = self.ocfl_service.convert_bundle_to_ocfl("test-bucket", "test/folder")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Failed to analyze folder")

    def test_convert_bundle_to_ocfl_not_feasible(self):
        """Test in-place conversion when not feasible"""
        analysis_result = {
            "success": True,
            "structure_analysis": {"is_ocfl_compliant": False}
        }

        conversion_plan = {
            "feasible": False,
            "risks": ["Unknown structure type"]
        }

        self.ocfl_service.analyze_folder_structure = Mock(return_value=analysis_result)
        self.ocfl_service.create_conversion_plan = Mock(return_value=conversion_plan)

        result = self.ocfl_service.convert_bundle_to_ocfl("test-bucket", "test/folder")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Conversion not feasible")

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_create_ocfl_structure_structured_to_ocfl(self, mock_file, mock_makedirs):
        """Test creating OCFL structure from structured legacy"""
        source_dir = "/tmp/source"
        target_dir = "/tmp/target"
        conversion_plan = {
            "conversion_type": "structured_to_ocfl",
            "preserve_items": ["acl.json", "metadata.xml"]
        }

        # Mock helper methods
        self.ocfl_service._find_and_move_xml_files = Mock(return_value=["metadata.xml"])
        self.ocfl_service._move_acl_file_if_exists = Mock(return_value=True)
        self.ocfl_service._move_resources_directory = Mock(return_value=5)

        result = self.ocfl_service._create_ocfl_structure(source_dir, target_dir, conversion_plan)

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 7)  # 1 XML + 1 ACL + 5 Resources
        self.assertEqual(result["structure_created"], "OCFL v1.0")

        # Verify OCFL marker was created
        mock_file.assert_called()
        mock_makedirs.assert_called()

    @patch('os.makedirs')
    @patch('builtins.open', new_callable=mock_open)
    def test_create_ocfl_structure_flat_to_ocfl(self, mock_file, mock_makedirs):
        """Test creating OCFL structure from flat legacy"""
        source_dir = "/tmp/source"
        target_dir = "/tmp/target"
        conversion_plan = {
            "conversion_type": "flat_to_ocfl"
        }

        # Mock helper method
        self.ocfl_service._organize_flat_structure = Mock(return_value=10)

        result = self.ocfl_service._create_ocfl_structure(source_dir, target_dir, conversion_plan)

        self.assertTrue(result["success"])
        self.assertEqual(result["files_processed"], 10)

    @patch('os.walk')
    @patch('shutil.copy2')
    def test_find_and_move_xml_files(self, mock_copy, mock_walk):
        """Test finding and moving XML files"""
        # Mock os.walk to return XML files
        mock_walk.return_value = [
            ("/tmp/source", [], ["metadata.xml", "description.xml", "file.txt"])
        ]

        result = self.ocfl_service._find_and_move_xml_files("/tmp/source", "/tmp/metadata")

        self.assertEqual(len(result), 2)
        self.assertIn("metadata.xml", result)
        self.assertIn("description.xml", result)

        # Verify copy2 was called for XML files only
        self.assertEqual(mock_copy.call_count, 2)

    @patch('os.path.exists')
    @patch('shutil.copy2')
    def test_move_acl_file_if_exists(self, mock_copy, mock_exists):
        """Test moving ACL file when it exists"""
        mock_exists.return_value = True

        result = self.ocfl_service._move_acl_file_if_exists("/tmp/source", "/tmp/metadata")

        self.assertTrue(result)
        mock_copy.assert_called_once()

    @patch('os.path.exists')
    def test_move_acl_file_if_exists_not_found(self, mock_exists):
        """Test moving ACL file when it doesn't exist"""
        mock_exists.return_value = False

        result = self.ocfl_service._move_acl_file_if_exists("/tmp/source", "/tmp/metadata")

        self.assertFalse(result)

    @patch('os.path.isdir')
    @patch('shutil.copytree')
    @patch('os.walk')
    def test_move_resources_directory(self, mock_walk, mock_copytree, mock_isdir):
        """Test moving Resources directory"""
        mock_isdir.return_value = True
        # Mock walk to count files in Resources
        mock_walk.return_value = [
            ("/tmp/source/Resources", [], ["file1.wav", "file2.wav", "file3.txt"])
        ]

        result = self.ocfl_service._move_resources_directory("/tmp/source", "/tmp/content")

        self.assertEqual(result, 3)  # 3 files in Resources
        mock_copytree.assert_called_once()

    @patch('os.path.isdir')
    def test_move_resources_directory_not_found(self, mock_isdir):
        """Test moving Resources directory when it doesn't exist"""
        mock_isdir.return_value = False

        result = self.ocfl_service._move_resources_directory("/tmp/source", "/tmp/content")

        self.assertEqual(result, 0)

    @patch('os.walk')
    @patch('os.makedirs')
    @patch('shutil.copy2')
    def test_organize_flat_structure(self, mock_copy, mock_makedirs, mock_walk):
        """Test organizing flat file structure"""
        # Mock os.walk to return mixed files
        mock_walk.return_value = [
            ("/tmp/source", [], ["metadata.xml", "acl.json", "audio.wav", "document.pdf"])
        ]

        result = self.ocfl_service._organize_flat_structure(
            "/tmp/source", "/tmp/content", "/tmp/metadata"
        )

        self.assertEqual(result, 4)  # 4 files processed
        # Verify copy2 was called for each file
        self.assertEqual(mock_copy.call_count, 4)

    def test_delete_folder_contents(self):
        """Test deleting folder contents from S3"""
        # Mock paginator and pages
        mock_paginator = Mock()
        mock_page1 = {
            "Contents": [
                {"Key": "test/folder/file1.txt"},
                {"Key": "test/folder/file2.txt"}
            ]
        }
        mock_page2 = {"Contents": [{"Key": "test/folder/subdir/file3.txt"}]}

        mock_paginator.paginate.return_value = [mock_page1, mock_page2]
        self.mock_bucket_service.s3_client.get_paginator.return_value = mock_paginator

        self.ocfl_service._delete_folder_contents("test-bucket", "test/folder")

        # Verify delete_objects was called
        self.mock_bucket_service.s3_client.delete_objects.assert_called()
        # Should be called twice (once per page)
        self.assertEqual(self.mock_bucket_service.s3_client.delete_objects.call_count, 2)

    def test_move_folder_contents(self):
        """Test moving folder contents in S3"""
        # Mock paginator
        mock_paginator = Mock()
        mock_page = {
            "Contents": [
                {"Key": "source/folder/file1.txt"},
                {"Key": "source/folder/subdir/file2.txt"}
            ]
        }

        mock_paginator.paginate.return_value = [mock_page]
        self.mock_bucket_service.s3_client.get_paginator.return_value = mock_paginator

        self.ocfl_service._move_folder_contents("test-bucket", "source/folder", "target/folder")

        # Verify copy_object was called for each file
        expected_calls = [
            call(
                CopySource={"Bucket": "test-bucket", "Key": "source/folder/file1.txt"},
                Bucket="test-bucket",
                Key="target/folder/file1.txt"
            ),
            call(
                CopySource={"Bucket": "test-bucket", "Key": "source/folder/subdir/file2.txt"},
                Bucket="test-bucket",
                Key="target/folder/subdir/file2.txt"
            )
        ]

        self.mock_bucket_service.s3_client.copy_object.assert_has_calls(expected_calls)

    @patch('lacos.storage.services.ocfl_service.logger')
    def test_delete_folder_contents_error(self, mock_logger):
        """Test error handling in delete folder contents"""
        self.mock_bucket_service.s3_client.get_paginator.side_effect = Exception("S3 error")

        with self.assertRaises(Exception):
            self.ocfl_service._delete_folder_contents("test-bucket", "test/folder")

        mock_logger.error.assert_called()

    @patch('lacos.storage.services.ocfl_service.logger')
    def test_move_folder_contents_error(self, mock_logger):
        """Test error handling in move folder contents"""
        self.mock_bucket_service.s3_client.get_paginator.side_effect = Exception("S3 error")

        with self.assertRaises(Exception):
            self.ocfl_service._move_folder_contents("test-bucket", "source", "target")

        mock_logger.error.assert_called()
