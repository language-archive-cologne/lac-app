import pytest
import time
from unittest.mock import Mock, patch
from django.test import TestCase
from concurrent.futures import Future

from lacos.storage.services.bucket_ocfl_processor import (
    BucketOCFLProcessor, ProcessingStatus, FolderProcessingResult, BatchProcessingProgress
)
from lacos.storage.services.bucket_structure_scanner import (
    BucketStructureScanner, FolderAnalysis, BucketAnalysis, StructureType
)


class TestBucketOCFLProcessor(TestCase):
    """Test cases for BucketOCFLProcessor"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_bucket_service = Mock()
        self.mock_ocfl_service = Mock()
        self.processor = BucketOCFLProcessor(self.mock_bucket_service, self.mock_ocfl_service)

        # Mock the scanner and fixture manager
        self.processor.scanner = Mock(spec=BucketStructureScanner)
        self.processor.fixture_manager = Mock()

    def test_process_all_collections_empty(self):
        """Test processing an empty bucket"""
        # Mock empty bucket analysis
        empty_analysis = BucketAnalysis(bucket_name="test-bucket")
        empty_analysis.folders = []

        self.processor.scanner.scan_bucket_structures.return_value = empty_analysis

        result = self.processor.process_all_collections("test-bucket")

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "No collections found to process")
        self.assertEqual(result["analysis"], empty_analysis)

    def test_process_all_collections_not_feasible(self):
        """Test processing when conversion is not feasible"""
        # Mock bucket analysis with blocking issues
        analysis = BucketAnalysis(bucket_name="test-bucket")
        folder = FolderAnalysis("test/folder", StructureType.UNKNOWN)
        analysis.folders = [folder]

        feasibility = {
            "feasible": False,
            "blocking_issues": ["Critical error"],
            "confidence": "low"
        }

        self.processor.scanner.scan_bucket_structures.return_value = analysis
        self.processor.scanner.validate_conversion_feasibility.return_value = feasibility

        result = self.processor.process_all_collections("test-bucket", dry_run=False)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Conversion not feasible")
        self.assertEqual(result["feasibility"], feasibility)

    def test_process_all_collections_dry_run(self):
        """Test dry run processing"""
        # Mock bucket analysis
        analysis = BucketAnalysis(bucket_name="test-bucket")
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)
        folder.conversion_complexity = "low"
        analysis.folders = [folder]

        feasibility = {"feasible": True, "confidence": "high"}

        self.processor.scanner.scan_bucket_structures.return_value = analysis
        self.processor.scanner.validate_conversion_feasibility.return_value = feasibility

        result = self.processor.process_all_collections("test-bucket", dry_run=True)

        self.assertTrue(result["success"])
        self.assertEqual(result["processing_summary"]["total_folders"], 1)

        # Verify no actual conversion methods were called
        self.processor.fixture_manager.create_fixture_backup.assert_not_called()
        self.mock_ocfl_service.convert_bundle_to_ocfl.assert_not_called()

    def test_process_all_collections_sequential(self):
        """Test sequential processing of collections"""
        # Mock bucket analysis
        analysis = BucketAnalysis(bucket_name="test-bucket")
        folder1 = FolderAnalysis("test/folder1", StructureType.LEGACY_STRUCTURED)
        folder1.conversion_complexity = "low"
        folder2 = FolderAnalysis("test/folder2", StructureType.LEGACY_FLAT)
        folder2.conversion_complexity = "medium"
        analysis.folders = [folder1, folder2]

        feasibility = {"feasible": True, "confidence": "high"}

        self.processor.scanner.scan_bucket_structures.return_value = analysis
        self.processor.scanner.validate_conversion_feasibility.return_value = feasibility

        # Mock successful conversions
        self.processor.fixture_manager.create_fixture_backup.return_value = "backup_123"
        self.mock_ocfl_service.convert_bundle_to_ocfl.return_value = {
            "success": True,
            "files_processed": 10
        }

        result = self.processor.process_all_collections("test-bucket", parallel=False)

        self.assertTrue(result["success"])
        self.assertEqual(result["processing_summary"]["total_folders"], 2)
        self.assertEqual(result["processing_summary"]["completed"], 2)
        self.assertEqual(result["processing_summary"]["failed"], 0)

        # Verify conversion was called for both collections
        self.assertEqual(self.mock_ocfl_service.convert_bundle_to_ocfl.call_count, 2)

    @patch('lacos.storage.services.bucket_ocfl_processor.ThreadPoolExecutor')
    def test_process_all_collections_parallel(self, mock_executor):
        """Test parallel processing of collections"""
        # Mock bucket analysis
        analysis = BucketAnalysis(bucket_name="test-bucket")
        folder1 = FolderAnalysis("test/folder1", StructureType.LEGACY_STRUCTURED)
        folder1.conversion_complexity = "low"
        folder2 = FolderAnalysis("test/folder2", StructureType.LEGACY_FLAT)
        folder2.conversion_complexity = "medium"
        analysis.folders = [folder1, folder2]

        feasibility = {"feasible": True, "confidence": "high"}

        self.processor.scanner.scan_bucket_structures.return_value = analysis
        self.processor.scanner.validate_conversion_feasibility.return_value = feasibility

        # Mock ThreadPoolExecutor
        mock_executor_instance = Mock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock futures
        future1 = Mock(spec=Future)
        future1.done.return_value = True
        future1.result.return_value = FolderProcessingResult(
            folder_path="test/folder1",
            status=ProcessingStatus.COMPLETED,
            files_processed=10
        )

        future2 = Mock(spec=Future)
        future2.done.return_value = True
        future2.result.return_value = FolderProcessingResult(
            folder_path="test/folder2",
            status=ProcessingStatus.COMPLETED,
            files_processed=5
        )

        mock_executor_instance.submit.side_effect = [future1, future2]

        # Mock as_completed to return futures in order
        with patch('lacos.storage.services.bucket_ocfl_processor.as_completed') as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]

            result = self.processor.process_all_collections("test-bucket", parallel=True)

            self.assertTrue(result["success"])
            self.assertEqual(result["processing_summary"]["total_folders"], 2)
            self.assertEqual(result["processing_summary"]["completed"], 2)

    def test_process_single_folder_already_compliant(self):
        """Test processing folder that's already OCFL compliant"""
        folder = FolderAnalysis("test/folder", StructureType.FULL_OCFL)

        result = self.processor._process_single_folder("test-bucket", folder, False)

        self.assertEqual(result.status, ProcessingStatus.SKIPPED)
        self.assertEqual(result.conversion_details["reason"], "Already OCFL compliant")

    def test_process_single_folder_dry_run(self):
        """Test processing folder in dry run mode"""
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)

        result = self.processor._process_single_folder("test-bucket", folder, True)

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertTrue(result.conversion_details["dry_run"])
        self.assertTrue(result.conversion_details["would_convert"])

    def test_process_single_folder_successful_conversion(self):
        """Test successful folder conversion"""
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)

        # Mock successful backup and conversion
        self.processor.fixture_manager.create_fixture_backup.return_value = "backup_123"
        self.mock_ocfl_service.convert_bundle_to_ocfl.return_value = {
            "success": True,
            "files_processed": 15,
            "message": "Conversion successful"
        }

        result = self.processor._process_single_folder("test-bucket", folder, False)

        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(result.backup_id, "backup_123")
        self.assertEqual(result.files_processed, 15)
        self.assertIn("backup_123", self.processor.active_backups)

    def test_process_single_folder_conversion_failure(self):
        """Test failed folder conversion"""
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)

        # Mock backup creation but failed conversion
        self.processor.fixture_manager.create_fixture_backup.return_value = "backup_123"
        self.mock_ocfl_service.convert_bundle_to_ocfl.return_value = {
            "success": False,
            "error": "Conversion failed due to invalid structure"
        }

        result = self.processor._process_single_folder("test-bucket", folder, False)

        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error_message, "Conversion failed due to invalid structure")
        self.assertEqual(result.backup_id, "backup_123")

    def test_process_single_folder_backup_failure(self):
        """Test processing when backup creation fails"""
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)

        # Mock backup failure but successful conversion
        self.processor.fixture_manager.create_fixture_backup.side_effect = Exception("Backup failed")
        self.mock_ocfl_service.convert_bundle_to_ocfl.return_value = {
            "success": True,
            "files_processed": 10
        }

        result = self.processor._process_single_folder("test-bucket", folder, False)

        # Should still complete successfully (risky but allowed)
        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertIsNone(result.backup_id)

    def test_process_single_folder_exception(self):
        """Test processing with unexpected exception"""
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)

        # Mock exception during processing
        self.mock_ocfl_service.convert_bundle_to_ocfl.side_effect = Exception("Unexpected error")

        result = self.processor._process_single_folder("test-bucket", folder, False)

        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertEqual(result.error_message, "Unexpected error")

    def test_get_processing_progress(self):
        """Test getting processing progress with rate calculation"""
        # Initialize progress
        self.processor.progress.start_time = time.time() - 60  # 1 minute ago
        self.processor.progress.total_folders = 10
        self.processor.progress.completed = 5

        progress = self.processor.get_processing_progress()

        self.assertEqual(progress.total_folders, 10)
        self.assertEqual(progress.completed, 5)
        self.assertGreater(progress.processing_rate, 0)  # Should be > 0 after 1 minute
        self.assertIsNotNone(progress.estimated_completion)

    def test_stop_processing(self):
        """Test stopping ongoing processing"""
        self.assertFalse(self.processor._stop_processing.is_set())

        self.processor.stop_processing()

        self.assertTrue(self.processor._stop_processing.is_set())

    def test_rollback_failed_conversions(self):
        """Test rolling back failed conversions"""
        # Set up active backups
        self.processor.active_backups = ["backup_1", "backup_2", "backup_3"]

        # Mock fixture manager rollback responses
        def mock_restore(backup_id, bucket):
            if backup_id == "backup_2":
                return {"success": False, "error": "Restore failed"}
            return {"success": True, "files_restored": 10}

        self.processor.fixture_manager.restore_from_backup.side_effect = mock_restore

        result = self.processor.rollback_failed_conversions("test-bucket")

        self.assertFalse(result["success"])  # One failure makes overall failure
        self.assertEqual(len(result["restored_folders"]), 2)
        self.assertEqual(len(result["failed_rollbacks"]), 1)
        self.assertEqual(result["total_backups"], 3)

    def test_rollback_failed_conversions_all_success(self):
        """Test rollback with all successful restores"""
        self.processor.active_backups = ["backup_1", "backup_2"]

        # Mock successful restores
        self.processor.fixture_manager.restore_from_backup.return_value = {
            "success": True,
            "files_restored": 10
        }

        result = self.processor.rollback_failed_conversions("test-bucket")

        self.assertTrue(result["success"])
        self.assertEqual(len(result["restored_folders"]), 2)
        self.assertEqual(len(result["failed_rollbacks"]), 0)

    def test_cleanup_successful_conversions(self):
        """Test cleaning up backups for successful conversions"""
        # Set up processing results with successful conversions
        result1 = FolderProcessingResult("folder1", ProcessingStatus.COMPLETED)
        result1.backup_id = "backup_1"

        result2 = FolderProcessingResult("folder2", ProcessingStatus.FAILED)
        result2.backup_id = "backup_2"

        result3 = FolderProcessingResult("folder3", ProcessingStatus.COMPLETED)
        result3.backup_id = "backup_3"

        self.processor.results = {
            "folder1": result1,
            "folder2": result2,
            "folder3": result3
        }

        self.processor.active_backups = ["backup_1", "backup_2", "backup_3"]

        # Mock fixture manager cleanup
        def mock_cleanup(backup_id):
            return backup_id != "backup_3"  # backup_3 fails to cleanup

        self.processor.fixture_manager.cleanup_backup.side_effect = mock_cleanup

        result = self.processor.cleanup_successful_conversions()

        self.assertFalse(result["success"])  # One failure makes overall failure
        self.assertEqual(len(result["cleaned_backups"]), 1)  # Only backup_1 (backup_2 was failed conversion)
        self.assertEqual(len(result["failed_cleanups"]), 1)  # backup_3 failed to cleanup

    def test_compile_final_results(self):
        """Test compiling final processing results"""
        # Create mock analysis and processing results
        analysis = BucketAnalysis(bucket_name="test-bucket")
        analysis.total_folders = 3

        feasibility = {"feasible": True, "confidence": "high"}

        processing_results = [
            FolderProcessingResult("folder1", ProcessingStatus.COMPLETED),
            FolderProcessingResult("folder2", ProcessingStatus.FAILED),
            FolderProcessingResult("folder3", ProcessingStatus.SKIPPED)
        ]

        processing_results[0].backup_id = "backup_1"

        processing_results[0].start_time = time.time() - 10
        processing_results[0].end_time = time.time()
        processing_results[0].files_processed = 15

        processing_results[1].start_time = time.time() - 5
        processing_results[1].end_time = time.time()
        processing_results[1].error_message = "Conversion failed"

        # Set up processor state
        self.processor.progress.total_folders = 3
        self.processor.progress.completed = 1
        self.processor.progress.failed = 1
        self.processor.progress.skipped = 1
        self.processor.progress.start_time = time.time() - 20

        self.processor.active_backups = ["backup_1", "backup_2"]

        final_results = self.processor._compile_final_results(
            analysis, feasibility, processing_results
        )

        self.assertFalse(final_results["success"])  # Failed conversions make it fail
        self.assertEqual(final_results["bucket_name"], "test-bucket")
        self.assertEqual(final_results["processing_summary"]["total_folders"], 3)
        self.assertEqual(final_results["processing_summary"]["completed"], 1)
        self.assertEqual(final_results["processing_summary"]["failed"], 1)
        self.assertEqual(final_results["processing_summary"]["skipped"], 1)
        self.assertEqual(final_results["active_backups"], 2)

        # Check folder results
        folder_results = final_results["folder_results"]
        self.assertEqual(len(folder_results), 3)

        completed_result = next(r for r in folder_results if r["status"] == "completed")
        self.assertEqual(completed_result["files_processed"], 15)
        self.assertTrue(completed_result["has_backup"])

        failed_result = next(r for r in folder_results if r["status"] == "failed")
        self.assertEqual(failed_result["error_message"], "Conversion failed")

        # Check recommendations
        self.assertIn("Some conversions failed", final_results["recommendations"][0])

    def test_compile_final_results_all_successful(self):
        """Test compiling results when all conversions succeed"""
        analysis = BucketAnalysis(bucket_name="test-bucket")
        feasibility = {"feasible": True}

        processing_results = [
            FolderProcessingResult("folder1", ProcessingStatus.COMPLETED),
            FolderProcessingResult("folder2", ProcessingStatus.COMPLETED)
        ]

        self.processor.progress.completed = 2
        self.processor.progress.failed = 0
        self.processor.progress.skipped = 0
        self.processor.active_backups = ["backup_1", "backup_2"]

        final_results = self.processor._compile_final_results(
            analysis, feasibility, processing_results
        )

        self.assertTrue(final_results["success"])
        self.assertIn("All conversions successful", final_results["recommendations"][0])

    def test_set_progress_callback(self):
        """Test setting progress callback"""
        callback_called = False

        def test_callback(progress):
            nonlocal callback_called
            callback_called = True

        self.processor.set_progress_callback(test_callback)

        # Manually trigger callback
        if self.processor.progress_callback:
            self.processor.progress_callback(self.processor.progress)

        self.assertTrue(callback_called)

    def test_reset_processing_state(self):
        """Test resetting processing state"""
        # Set some state
        self.processor.progress.completed = 5
        self.processor.results = {"test": "result"}
        self.processor.active_backups = ["backup1"]
        self.processor._stop_processing.set()

        self.processor._reset_processing_state()

        self.assertEqual(self.processor.progress.completed, 0)
        self.assertEqual(len(self.processor.results), 0)
        self.assertEqual(len(self.processor.active_backups), 0)
        self.assertFalse(self.processor._stop_processing.is_set())

    def test_process_with_progress_callback(self):
        """Test processing with progress callback"""
        callback_calls = []

        def progress_callback(progress):
            callback_calls.append(progress.completed)

        self.processor.set_progress_callback(progress_callback)

        # Mock minimal successful processing
        analysis = BucketAnalysis(bucket_name="test-bucket")
        folder = FolderAnalysis("test/folder", StructureType.LEGACY_STRUCTURED)
        analysis.folders = [folder]

        feasibility = {"feasible": True}

        self.processor.scanner.scan_bucket_structures.return_value = analysis
        self.processor.scanner.validate_conversion_feasibility.return_value = feasibility
        self.mock_ocfl_service.convert_bundle_to_ocfl.return_value = {"success": True}

        result = self.processor.process_all_collections("test-bucket")

        self.assertTrue(result["success"])
        # Progress callback should have been called at least once
        self.assertGreater(len(callback_calls), 0)
