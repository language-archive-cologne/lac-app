import pytest
import json
from unittest.mock import Mock, patch
from django.test import TestCase

from lacos.storage.services.bucket_structure_scanner import (
    BucketStructureScanner, StructureType, FolderAnalysis, BucketAnalysis
)


class TestBucketStructureScanner(TestCase):
    """Test cases for BucketStructureScanner"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_bucket_service = Mock()
        self.scanner = BucketStructureScanner(self.mock_bucket_service)

    def test_analyze_folder_structure_full_ocfl(self):
        """Test analysis of a complete OCFL structure"""
        # Mock folder contents with full OCFL structure
        contents = [
            {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
            {"name": "v1", "is_dir": True},
            {"name": "content", "is_dir": True},
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "acl.json", "is_dir": False, "size": 256}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.FULL_OCFL)
        self.assertTrue(result.has_ocfl_marker)
        self.assertTrue(result.has_version_directory)
        self.assertTrue(result.has_content_directory)
        self.assertTrue(result.has_metadata_files)
        self.assertTrue(result.has_acl_file)
        self.assertEqual(result.total_files, 3)
        self.assertEqual(result.conversion_complexity, "low")

    def test_analyze_folder_structure_partial_ocfl(self):
        """Test analysis of a partial OCFL structure"""
        contents = [
            {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "data", "is_dir": True}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.PARTIAL_OCFL)
        self.assertTrue(result.has_ocfl_marker)
        self.assertFalse(result.has_version_directory)
        self.assertTrue(result.has_data_directory)
        self.assertEqual(result.conversion_complexity, "medium")

    def test_analyze_folder_structure_legacy_structured(self):
        """Test analysis of a legacy structured folder"""
        contents = [
            {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "description.xml", "is_dir": False, "size": 512},
            {"name": "data", "is_dir": True},
            {"name": "acl.json", "is_dir": False, "size": 256}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.LEGACY_STRUCTURED)
        self.assertFalse(result.has_ocfl_marker)
        self.assertTrue(result.has_metadata_files)
        self.assertTrue(result.has_data_directory)
        self.assertTrue(result.has_acl_file)
        self.assertEqual(len(result.xml_files), 2)
        self.assertEqual(result.conversion_complexity, "low")

    def test_analyze_folder_structure_legacy_flat(self):
        """Test analysis of a legacy flat structure"""
        contents = [
            {"name": "file1.txt", "is_dir": False, "size": 100},
            {"name": "file2.wav", "is_dir": False, "size": 5000},
            {"name": "metadata.xml", "is_dir": False, "size": 512}
        ]

        self.mock_bucket_service.list_bucket_contents.return_value = contents

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.LEGACY_FLAT)
        self.assertFalse(result.has_ocfl_marker)
        self.assertTrue(result.has_metadata_files)
        self.assertFalse(result.has_data_directory)
        self.assertEqual(result.total_files, 3)
        self.assertEqual(result.conversion_complexity, "medium")

    def test_analyze_folder_structure_empty(self):
        """Test analysis of an empty folder"""
        self.mock_bucket_service.list_bucket_contents.return_value = []

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.UNKNOWN)
        self.assertIn("Empty folder", result.issues)
        self.assertEqual(result.total_files, 0)

    @patch('lacos.storage.services.bucket_structure_scanner.logger')
    def test_analyze_folder_structure_error_handling(self, mock_logger):
        """Test error handling in folder analysis"""
        self.mock_bucket_service.list_bucket_contents.side_effect = Exception("S3 error")

        result = self.scanner.analyze_folder_structure("test-bucket", "test/folder")

        self.assertEqual(result.structure_type, StructureType.UNKNOWN)
        self.assertIn("Analysis error: S3 error", result.issues)
        self.assertEqual(result.conversion_complexity, "high")
        mock_logger.error.assert_called()

    def test_scan_bucket_structures(self):
        """Test scanning entire bucket structures"""
        # Mock top-level collections
        top_level_contents = [
            {"name": "folder1", "is_dir": True},
            {"name": "folder2", "is_dir": True},
            {"name": "folder3", "is_dir": True}
        ]

        # Mock individual folder contents
        folder_contents = {
            "folder1": [
                {"name": "0=ocfl_object_1.0", "is_dir": False, "size": 0},
                {"name": "v1", "is_dir": True},
                {"name": "content", "is_dir": True}
            ],
            "folder2": [
                {"name": "metadata.xml", "is_dir": False, "size": 1024},
            {"name": "data", "is_dir": True}
            ],
            "folder3": [
                {"name": "file.txt", "is_dir": False, "size": 100}
            ]
        }

        def mock_list_contents(bucket, prefix):
            if prefix == "":
                return top_level_contents
            else:
                return folder_contents.get(prefix, [])

        self.mock_bucket_service.list_bucket_contents.side_effect = mock_list_contents

        analysis = self.scanner.scan_bucket_structures("test-bucket")

        self.assertEqual(analysis.bucket_name, "test-bucket")
        self.assertEqual(analysis.total_folders, 3)
        self.assertEqual(len(analysis.folders), 3)

        # Check structure breakdown
        self.assertEqual(analysis.structure_breakdown[StructureType.FULL_OCFL], 1)
        self.assertEqual(analysis.structure_breakdown[StructureType.LEGACY_STRUCTURED], 1)
        self.assertEqual(analysis.structure_breakdown[StructureType.LEGACY_FLAT], 1)

    def test_create_conversion_plan(self):
        """Test creation of conversion plan"""
        # Create a bucket analysis with mixed structures
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 3

        # Add folders with different complexities
        folder1 = FolderAnalysis(folder_path="folder1", structure_type=StructureType.FULL_OCFL)
        folder1.conversion_complexity = "low"

        folder2 = FolderAnalysis(folder_path="folder2", structure_type=StructureType.LEGACY_STRUCTURED)
        folder2.conversion_complexity = "low"

        folder3 = FolderAnalysis(folder_path="folder3", structure_type=StructureType.LEGACY_FLAT)
        folder3.conversion_complexity = "medium"

        analysis.folders = [folder1, folder2, folder3]

        plan = self.scanner.create_conversion_plan(analysis)

        self.assertTrue(plan["conversion_feasible"])
        self.assertEqual(plan["total_folders"], 3)
        self.assertEqual(len(plan["conversion_phases"]), 2)  # Low and medium complexity phases

        # Check phases
        phase1 = plan["conversion_phases"][0]
        self.assertEqual(phase1["name"], "Low Complexity Conversions")
        self.assertEqual(len(phase1["folders"]), 2)  # folder1 (skip) + folder2

        phase2 = plan["conversion_phases"][1]
        self.assertEqual(phase2["name"], "Medium Complexity Conversions")
        self.assertEqual(len(phase2["folders"]), 1)  # folder3

    def test_validate_conversion_feasibility_high_success_rate(self):
        """Test feasibility validation with high success rate"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 10
        analysis.blocking_issues = []

        # Add folders with good structure
        for i in range(10):
            folder = FolderAnalysis(f"folder{i}", StructureType.LEGACY_STRUCTURED)
            folder.conversion_complexity = "low"
            analysis.folders.append(folder)

        result = self.scanner.validate_conversion_feasibility(analysis)

        self.assertTrue(result["feasible"])
        self.assertEqual(result["confidence"], "high")
        self.assertGreaterEqual(result["estimated_success_rate"], 90)

    def test_validate_conversion_feasibility_with_blocking_issues(self):
        """Test feasibility validation with blocking issues"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 5
        analysis.blocking_issues = ["Critical error in folder1", "Access denied to folder2"]

        result = self.scanner.validate_conversion_feasibility(analysis)

        self.assertFalse(result["feasible"])
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["estimated_success_rate"], 20)
        self.assertEqual(len(result["blocking_issues"]), 2)

    def test_validate_conversion_feasibility_unknown_structures(self):
        """Test feasibility validation with many unknown structures"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 10
        analysis.blocking_issues = []

        # Add folders with unknown structures (30% unknown)
        for i in range(7):
            folder = FolderAnalysis(f"folder{i}", StructureType.LEGACY_STRUCTURED)
            analysis.folders.append(folder)

        for i in range(3):
            folder = FolderAnalysis(f"unknown{i}", StructureType.UNKNOWN)
            analysis.folders.append(folder)

        analysis.structure_breakdown = {
            StructureType.LEGACY_STRUCTURED: 7,
            StructureType.UNKNOWN: 3,
            StructureType.FULL_OCFL: 0,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.MIXED: 0
        }

        result = self.scanner.validate_conversion_feasibility(analysis)

        self.assertTrue(result["feasible"])  # Still feasible but with warnings
        self.assertEqual(result["confidence"], "medium")
        self.assertIn("30.0% of folders have unknown structure", result["warnings"])

    def test_determine_structure_type_edge_cases(self):
        """Test structure type determination for edge cases"""
        # Test mixed structure indicators
        analysis = FolderAnalysis("test", StructureType.UNKNOWN)
        analysis.has_ocfl_marker = True
        analysis.has_metadata_files = True
        analysis.has_data_directory = False
        analysis.has_version_directory = False

        structure_type = self.scanner._determine_structure_type(analysis)
        self.assertEqual(structure_type, StructureType.PARTIAL_OCFL)

        # Test empty structure
        analysis = FolderAnalysis("test", StructureType.UNKNOWN)
        analysis.total_files = 0

        structure_type = self.scanner._determine_structure_type(analysis)
        self.assertEqual(structure_type, StructureType.UNKNOWN)

    def test_conversion_complexity_assessment(self):
        """Test conversion complexity assessment"""
        # Test already compliant (low complexity)
        analysis = FolderAnalysis("test", StructureType.FULL_OCFL)
        complexity = self.scanner._assess_conversion_complexity(analysis)
        self.assertEqual(complexity, "low")

        # Test partial OCFL (medium complexity)
        analysis = FolderAnalysis("test", StructureType.PARTIAL_OCFL)
        complexity = self.scanner._assess_conversion_complexity(analysis)
        self.assertEqual(complexity, "medium")

        # Test unknown structure (high complexity)
        analysis = FolderAnalysis("test", StructureType.UNKNOWN)
        complexity = self.scanner._assess_conversion_complexity(analysis)
        self.assertEqual(complexity, "high")

    def test_folder_recommendations_generation(self):
        """Test generation of folder-specific recommendations"""
        # Test already compliant folder
        analysis = FolderAnalysis("test", StructureType.FULL_OCFL)
        self.scanner._generate_folder_recommendations(analysis)
        self.assertIn("Already OCFL-compliant", analysis.recommendations[0])

        # Test partial OCFL folder
        analysis = FolderAnalysis("test", StructureType.PARTIAL_OCFL)
        analysis.has_content_directory = False
        self.scanner._generate_folder_recommendations(analysis)
        self.assertIn("Complete existing OCFL structure", analysis.recommendations[0])
        self.assertIn("Add v1/content directory structure", analysis.recommendations[1])

        # Test legacy structured folder with ACL
        analysis = FolderAnalysis("test", StructureType.LEGACY_STRUCTURED)
        analysis.has_acl_file = True
        self.scanner._generate_folder_recommendations(analysis)
        self.assertIn("Convert to OCFL preserving existing structure", analysis.recommendations[0])
        self.assertIn("Preserve ACL file in metadata directory", analysis.recommendations[1])

    def test_bucket_recommendations_generation(self):
        """Test generation of bucket-level recommendations"""
        analysis = BucketAnalysis(bucket_name="test-bucket")

        # Test mostly OCFL-compliant bucket
        analysis.total_folders = 10
        analysis.structure_breakdown = {
            StructureType.FULL_OCFL: 9,
            StructureType.LEGACY_STRUCTURED: 1,
            StructureType.PARTIAL_OCFL: 0,
            StructureType.LEGACY_FLAT: 0,
            StructureType.UNKNOWN: 0,
            StructureType.MIXED: 0
        }

        self.scanner._generate_bucket_recommendations(analysis)
        self.assertEqual(analysis.conversion_feasibility, "high")
        self.assertIn("Most folders already OCFL-compliant", analysis.recommendations[0])

        # Test bucket with blocking issues
        analysis.blocking_issues = ["Critical error"]
        analysis.recommendations = []  # Reset

        self.scanner._generate_bucket_recommendations(analysis)
        self.assertEqual(analysis.conversion_feasibility, "low")
        self.assertIn("Resolve blocking issues before conversion", analysis.recommendations[0])

    def test_time_estimation(self):
        """Test conversion time estimation"""
        analysis = BucketAnalysis(bucket_name="test-bucket")

        # Add folders with different complexities
        for i in range(5):
            folder = FolderAnalysis(f"low{i}", StructureType.LEGACY_STRUCTURED)
            folder.conversion_complexity = "low"
            analysis.folders.append(folder)

        for i in range(2):
            folder = FolderAnalysis(f"medium{i}", StructureType.LEGACY_FLAT)
            folder.conversion_complexity = "medium"
            analysis.folders.append(folder)

        for i in range(1):
            folder = FolderAnalysis(f"high{i}", StructureType.UNKNOWN)
            folder.conversion_complexity = "high"
            analysis.folders.append(folder)

        self.scanner._generate_bucket_recommendations(analysis)

        # Expected: (5 * 2) + (2 * 5) + (1 * 15) = 35 minutes
        self.assertEqual(analysis.estimated_conversion_time, "35 minutes")

        # Test hours conversion
        analysis.folders = []
        for i in range(100):  # Many folders to exceed 60 minutes
            folder = FolderAnalysis(f"folder{i}", StructureType.LEGACY_STRUCTURED)
            folder.conversion_complexity = "low"
            analysis.folders.append(folder)

        self.scanner._generate_bucket_recommendations(analysis)
        self.assertIn("hours", analysis.estimated_conversion_time)
