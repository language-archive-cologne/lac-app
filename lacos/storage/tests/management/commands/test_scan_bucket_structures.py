import pytest
import json
import yaml
import tempfile
import os
from unittest.mock import Mock, patch
from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from lacos.storage.management.commands.scan_bucket_structures import Command
from lacos.storage.services.bucket_structure_scanner import BucketAnalysis, FolderAnalysis, StructureType


class TestScanBucketStructuresCommand(TestCase):
    """Test cases for scan_bucket_structures management command"""

    def setUp(self):
        """Set up test fixtures"""
        self.command = Command()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures"""
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_text_output(self, mock_scanner_class, mock_bucket_service_class):
        """Test command with text output format"""
        # Create mock analysis
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 3
        analysis.total_files = 150
        analysis.total_size = 1024 * 1024 * 10  # 10MB
        analysis.conversion_feasibility = "high"
        analysis.estimated_conversion_time = "15 minutes"
        analysis.structure_breakdown = {
            StructureType.FULL_OCFL: 1,
            StructureType.LEGACY_STRUCTURED: 2,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }
        analysis.blocking_issues = []
        analysis.recommendations = ["Good structure", "Consider bulk conversion"]

        # Mock scanner
        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.return_value = analysis
        mock_scanner_class.return_value = mock_scanner

        out = StringIO()
        call_command('scan_bucket_structures', 'test-bucket', stdout=out)

        output = out.getvalue()
        self.assertIn("test-bucket", output)
        self.assertIn("Total folders: 3", output)
        self.assertIn("Total files: 150", output)
        self.assertIn("10.0 MB", output)
        self.assertIn("Conversion feasibility: high", output)
        self.assertIn("full_ocfl: 1", output)
        self.assertIn("legacy_structured: 2", output)
        self.assertIn("Good structure", output)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_json_output(self, mock_scanner_class, mock_bucket_service_class):
        """Test command with JSON output format"""
        # Create mock analysis
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 2
        analysis.total_files = 50
        analysis.total_size = 1024 * 1024  # 1MB
        analysis.conversion_feasibility = "medium"
        analysis.estimated_conversion_time = "5 minutes"
        analysis.structure_breakdown = {
            StructureType.LEGACY_STRUCTURED: 2,
            StructureType.FULL_OCFL: 0,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }
        analysis.blocking_issues = ["Issue 1"]
        analysis.recommendations = ["Recommendation 1"]

        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.return_value = analysis
        mock_scanner_class.return_value = mock_scanner

        out = StringIO()
        call_command('scan_bucket_structures', 'test-bucket', '--output-format=json', stdout=out)

        output = out.getvalue()
        data = json.loads(output)

        self.assertEqual(data["bucket_name"], "test-bucket")
        self.assertEqual(data["total_folders"], 2)
        self.assertEqual(data["total_files"], 50)
        self.assertEqual(data["total_size"], 1024 * 1024)
        self.assertEqual(data["conversion_feasibility"], "medium")
        self.assertEqual(data["structure_breakdown"]["legacy_structured"], 2)
        self.assertEqual(len(data["blocking_issues"]), 1)
        self.assertEqual(len(data["recommendations"]), 1)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_yaml_output(self, mock_scanner_class, mock_bucket_service_class):
        """Test command with YAML output format"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 1
        analysis.structure_breakdown = {
            StructureType.FULL_OCFL: 1,
            StructureType.LEGACY_STRUCTURED: 0,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }

        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.return_value = analysis
        mock_scanner_class.return_value = mock_scanner

        out = StringIO()
        call_command('scan_bucket_structures', 'test-bucket', '--output-format=yaml', stdout=out)

        output = out.getvalue()
        data = yaml.safe_load(output)

        self.assertEqual(data["bucket_name"], "test-bucket")
        self.assertEqual(data["total_folders"], 1)
        self.assertEqual(data["structure_breakdown"]["full_ocfl"], 1)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_detailed_output(self, mock_scanner_class, mock_bucket_service_class):
        """Test command with detailed folder analysis"""
        # Create mock analysis with folders
        analysis = BucketAnalysis(bucket_name="test-bucket")

        folder1 = FolderAnalysis("folder1", StructureType.FULL_OCFL)
        folder1.total_files = 10
        folder1.total_size = 1024
        folder1.has_ocfl_marker = True
        folder1.has_version_directory = True
        folder1.has_content_directory = True
        folder1.xml_files = ["metadata.xml"]
        folder1.conversion_complexity = "low"
        folder1.recommendations = ["Already compliant"]

        folder2 = FolderAnalysis("folder2", StructureType.LEGACY_STRUCTURED)
        folder2.total_files = 5
        folder2.total_size = 512
        folder2.has_metadata_files = True
        folder2.has_data_directory = True
        folder2.xml_files = ["desc.xml"]
        folder2.conversion_complexity = "low"
        folder2.issues = ["Needs conversion"]

        analysis.folders = [folder1, folder2]
        analysis.total_folders = 2

        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.return_value = analysis
        mock_scanner_class.return_value = mock_scanner

        out = StringIO()
        call_command(
            'scan_bucket_structures', 'test-bucket',
            '--output-format=json', '--detailed',
            stdout=out
        )

        output = out.getvalue()
        data = json.loads(output)

        self.assertIn("folders", data)
        self.assertEqual(len(data["folders"]), 2)

        # Check folder1 details
        folder1_data = data["folders"][0]
        self.assertEqual(folder1_data["folder_path"], "folder1")
        self.assertEqual(folder1_data["structure_type"], "full_ocfl")
        self.assertTrue(folder1_data["has_ocfl_marker"])
        self.assertEqual(len(folder1_data["xml_files"]), 1)

        # Check folder2 details
        folder2_data = data["folders"][1]
        self.assertEqual(folder2_data["folder_path"], "folder2")
        self.assertEqual(folder2_data["structure_type"], "legacy_structured")
        self.assertEqual(len(folder2_data["issues"]), 1)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_output_to_file(self, mock_scanner_class, mock_bucket_service_class):
        """Test command writing output to file"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 1

        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.return_value = analysis
        mock_scanner_class.return_value = mock_scanner

        output_file = os.path.join(self.temp_dir, "analysis.json")

        out = StringIO()
        call_command(
            'scan_bucket_structures', 'test-bucket',
            '--output-format=json', f'--output-file={output_file}',
            stdout=out
        )

        # Verify file was created
        self.assertTrue(os.path.exists(output_file))

        # Verify file content
        with open(output_file, 'r') as f:
            data = json.load(f)
            self.assertEqual(data["bucket_name"], "test-bucket")

        # Verify success message
        output = out.getvalue()
        self.assertIn(f"Analysis written to {output_file}", output)

    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketService')
    @patch('lacos.storage.management.commands.scan_bucket_structures.BucketStructureScanner')
    def test_command_scanner_error(self, mock_scanner_class, mock_bucket_service_class):
        """Test command handling scanner errors"""
        mock_scanner = Mock()
        mock_scanner.scan_bucket_structures.side_effect = Exception("Scanner error")
        mock_scanner_class.return_value = mock_scanner

        with self.assertRaises(CommandError) as cm:
            call_command('scan_bucket_structures', 'test-bucket')

        self.assertIn("Scanner error", str(cm.exception))

    def test_format_size(self):
        """Test size formatting utility"""
        # Test bytes
        self.assertEqual(self.command._format_size(512), "512 B")

        # Test KB
        self.assertEqual(self.command._format_size(1536), "1.5 KB")

        # Test MB
        self.assertEqual(self.command._format_size(1024 * 1024 * 2.5), "2.5 MB")

        # Test GB
        self.assertEqual(self.command._format_size(1024 * 1024 * 1024 * 1.5), "1.5 GB")

    def test_format_text_output_detailed(self):
        """Test detailed text output formatting"""
        # Create analysis with detailed folder data
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 2
        analysis.total_files = 100
        analysis.total_size = 1024 * 1024 * 5  # 5MB
        analysis.conversion_feasibility = "high"
        analysis.estimated_conversion_time = "10 minutes"
        analysis.structure_breakdown = {
            StructureType.FULL_OCFL: 1,
            StructureType.LEGACY_STRUCTURED: 1,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }
        analysis.blocking_issues = ["Critical issue"]
        analysis.recommendations = ["Fix issues first", "Then proceed"]

        # Create detailed folders
        folder1 = FolderAnalysis("test/folder1", StructureType.FULL_OCFL)
        folder1.total_files = 50
        folder1.total_size = 1024 * 1024 * 3
        folder1.conversion_complexity = "low"
        folder1.has_ocfl_marker = True
        folder1.has_version_directory = True
        folder1.has_content_directory = True
        folder1.xml_files = ["metadata.xml", "description.xml"]
        folder1.has_acl_file = True
        folder1.recommendations = ["Already compliant"]

        folder2 = FolderAnalysis("test/folder2", StructureType.LEGACY_STRUCTURED)
        folder2.total_files = 50
        folder2.total_size = 1024 * 1024 * 2
        folder2.conversion_complexity = "medium"
        folder2.has_metadata_files = True
        folder2.has_data_directory = True
        folder2.xml_files = ["data.xml"]
        folder2.issues = ["Missing ACL"]
        folder2.recommendations = ["Add ACL file", "Convert to OCFL"]

        analysis.folders = [folder1, folder2]

        output = self.command._format_text_output(analysis, detailed=True)

        # Check summary section
        self.assertIn("Bucket Structure Analysis: test-bucket", output)
        self.assertIn("Total folders: 2", output)
        self.assertIn("Total files: 100", output)
        self.assertIn("5.0 MB", output)
        self.assertIn("Conversion feasibility: high", output)

        # Check structure breakdown
        self.assertIn("full_ocfl: 1 (50.0%)", output)
        self.assertIn("legacy_structured: 1 (50.0%)", output)

        # Check blocking issues
        self.assertIn("Critical issue", output)

        # Check recommendations
        self.assertIn("Fix issues first", output)
        self.assertIn("Then proceed", output)

        # Check detailed folder analysis
        self.assertIn("Detailed Folder Analysis:", output)
        self.assertIn("Folder: test/folder1", output)
        self.assertIn("Structure type: full_ocfl", output)
        self.assertIn("Conversion complexity: low", output)
        self.assertIn("OCFL components: OCFL marker, version directory, content directory", output)
        self.assertIn("Content: ACL file", output)
        self.assertIn("Already compliant", output)

        self.assertIn("Folder: test/folder2", output)
        self.assertIn("Structure type: legacy_structured", output)
        self.assertIn("Content: 1 XML files, data directory", output)
        self.assertIn("Issues: Missing ACL", output)
        self.assertIn("Add ACL file; Convert to OCFL", output)

    def test_format_json_output(self):
        """Test JSON output formatting"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 1
        analysis.total_files = 10
        analysis.total_size = 1024
        analysis.conversion_feasibility = "high"
        analysis.estimated_conversion_time = "2 minutes"
        analysis.structure_breakdown = {
            StructureType.FULL_OCFL: 1,
            StructureType.LEGACY_STRUCTURED: 0,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }
        analysis.blocking_issues = []
        analysis.recommendations = ["All good"]

        output_data = self.command._format_json_output(analysis, detailed=False)

        self.assertEqual(output_data["bucket_name"], "test-bucket")
        self.assertEqual(output_data["total_folders"], 1)
        self.assertEqual(output_data["total_files"], 10)
        self.assertEqual(output_data["total_size"], 1024)
        self.assertEqual(output_data["conversion_feasibility"], "high")
        self.assertEqual(output_data["structure_breakdown"]["full_ocfl"], 1)
        self.assertEqual(len(output_data["blocking_issues"]), 0)
        self.assertEqual(len(output_data["recommendations"]), 1)

        # Detailed should not be included when detailed=False
        self.assertNotIn("folders", output_data)

    def test_format_json_output_detailed(self):
        """Test detailed JSON output formatting"""
        analysis = BucketAnalysis(bucket_name="test-bucket")

        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)
        folder.total_files = 5
        folder.total_size = 512
        folder.conversion_complexity = "low"
        folder.has_metadata_files = True
        folder.xml_files = ["metadata.xml"]
        folder.preservation_requirements = ["XML metadata"]
        folder.issues = ["Minor issue"]
        folder.recommendations = ["Convert"]

        analysis.folders = [folder]

        output_data = self.command._format_json_output(analysis, detailed=True)

        self.assertIn("folders", output_data)
        self.assertEqual(len(output_data["folders"]), 1)

        folder_data = output_data["folders"][0]
        self.assertEqual(folder_data["folder_path"], "test/folder")
        self.assertEqual(folder_data["structure_type"], "legacy_structured")
        self.assertEqual(folder_data["total_files"], 5)
        self.assertEqual(folder_data["conversion_complexity"], "low")
        self.assertTrue(folder_data["has_metadata_files"])
        self.assertEqual(len(folder_data["xml_files"]), 1)
        self.assertEqual(len(folder_data["issues"]), 1)
        self.assertEqual(len(folder_data["recommendations"]), 1)
