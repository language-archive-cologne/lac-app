import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .bucket_structure_scanner import BucketStructureScanner, BucketAnalysis, StructureType
from .ocfl_fixture_manager import OCFLFixtureManager
from .ocfl_service import OCFLService

logger = logging.getLogger(__name__)


class ProcessingStatus(Enum):
    """Status of folder processing"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FolderProcessingResult:
    """Result of processing a single folder"""
    folder_path: str
    status: ProcessingStatus
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    backup_id: Optional[str] = None
    files_processed: int = 0
    conversion_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchProcessingProgress:
    """Progress tracking for batch processing"""
    total_folders: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    in_progress: int = 0
    start_time: Optional[float] = None
    estimated_completion: Optional[float] = None
    current_folder: Optional[str] = None
    processing_rate: float = 0.0  # folders per minute
    errors: List[str] = field(default_factory=list)


class BucketOCFLProcessor:
    """
    Processor for handling bucket-wide OCFL conversions.
    Manages batch processing, progress tracking, and rollback capabilities.
    """

    def __init__(self, bucket_service, ocfl_service: OCFLService):
        """
        Initialize the bucket processor.

        Args:
            bucket_service: BucketService instance for S3 operations
            ocfl_service: OCFLService instance for OCFL operations
        """
        self.bucket_service = bucket_service
        self.ocfl_service = ocfl_service
        self.scanner = BucketStructureScanner(bucket_service)
        self.fixture_manager = OCFLFixtureManager(bucket_service)

        # Processing state
        self.progress = BatchProcessingProgress()
        self.results: Dict[str, FolderProcessingResult] = {}
        self.active_backups: List[str] = []

        # Threading
        self._processing_lock = threading.Lock()
        self._stop_processing = threading.Event()

        # Callbacks for progress reporting
        self.progress_callback: Optional[Callable[[BatchProcessingProgress], None]] = None

    def process_all_collections(self, bucket_name: str,
                                dry_run: bool = False,
                                parallel: bool = False,
                                max_workers: int = 3) -> Dict[str, Any]:
        """
        Process every collection in a bucket for OCFL-compliant bundles.

        Args:
            bucket_name (str): Name of bucket to process
            dry_run (bool): If True, only analyze without making changes
            parallel (bool): If True, process collections in parallel
            max_workers (int): Maximum number of parallel workers

        Returns:
            Dict containing processing results
        """
        logger.info("Starting collection-wide OCFL processing",
                   extra={"bucket_name": bucket_name, "dry_run": dry_run, "parallel": parallel})

        try:
            # Reset processing state
            self._reset_processing_state()

            # Scan bucket structures first
            analysis = self.scanner.scan_bucket_structures(bucket_name)

            if not analysis.folders:
                return {
                    "success": True,
                    "message": "No collections found to process",
                    "analysis": analysis
                }

            # Validate conversion feasibility
            feasibility = self.scanner.validate_conversion_feasibility(analysis)

            if not feasibility["feasible"] and not dry_run:
                return {
                    "success": False,
                    "error": "Conversion not feasible",
                    "feasibility": feasibility,
                    "analysis": analysis
                }

            # Initialize progress tracking
            self.progress.total_folders = len(analysis.folders)
            self.progress.start_time = time.time()

            # Process collections
            if parallel and not dry_run:
                processing_results = self._process_folders_parallel(
                    bucket_name, analysis.folders, max_workers
                )
            else:
                processing_results = self._process_folders_sequential(
                    bucket_name, analysis.folders, dry_run
                )

            # Calculate final results
            return self._compile_final_results(analysis, feasibility, processing_results)

        except Exception as e:
            logger.error("Error in bucket processing", extra={"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "progress": self.progress
            }

    def scan_bucket_structures(self, bucket_name: str) -> BucketAnalysis:
        """
        Scan and analyze bucket structures.

        Args:
            bucket_name (str): Name of bucket to scan

        Returns:
            BucketAnalysis: Analysis results
        """
        return self.scanner.scan_bucket_structures(bucket_name)

    def validate_conversion_feasibility(self, bucket_analysis: BucketAnalysis) -> Dict[str, Any]:
        """
        Validate if bucket conversion is feasible.

        Args:
            bucket_analysis: BucketAnalysis from scan

        Returns:
            Dict containing feasibility assessment
        """
        return self.scanner.validate_conversion_feasibility(bucket_analysis)

    def get_processing_progress(self) -> BatchProcessingProgress:
        """
        Get current processing progress.

        Returns:
            BatchProcessingProgress: Current progress state
        """
        with self._processing_lock:
            # Update processing rate
            if self.progress.start_time and self.progress.completed > 0:
                elapsed = time.time() - self.progress.start_time
                self.progress.processing_rate = (self.progress.completed / elapsed) * 60  # per minute

                # Estimate completion time
                remaining = self.progress.total_folders - self.progress.completed
                if self.progress.processing_rate > 0:
                    estimated_remaining_minutes = remaining / self.progress.processing_rate
                    self.progress.estimated_completion = time.time() + (estimated_remaining_minutes * 60)

            return self.progress

    def stop_processing(self) -> None:
        """Stop ongoing processing"""
        logger.info("Stopping bucket processing")
        self._stop_processing.set()

    def rollback_failed_conversions(self, bucket_name: str) -> Dict[str, Any]:
        """
        Rollback failed conversions using backups.

        Args:
            bucket_name (str): Name of bucket

        Returns:
            Dict containing rollback results
        """
        logger.info("Rolling back failed conversions", extra={"bucket_name": bucket_name})

        rollback_results = {
            "success": True,
            "restored_folders": [],
            "failed_rollbacks": [],
            "total_backups": len(self.active_backups)
        }

        try:
            for backup_id in self.active_backups:
                try:
                    result = self.fixture_manager.restore_from_backup(backup_id, bucket_name)
                    if result["success"]:
                        rollback_results["restored_folders"].append({
                            "backup_id": backup_id,
                            "files_restored": result.get("files_restored", 0)
                        })
                    else:
                        rollback_results["failed_rollbacks"].append({
                            "backup_id": backup_id,
                            "error": result["error"]
                        })
                except Exception as e:
                    rollback_results["failed_rollbacks"].append({
                        "backup_id": backup_id,
                        "error": str(e)
                    })

            if rollback_results["failed_rollbacks"]:
                rollback_results["success"] = False

            # Clean up backups after rollback
            self._cleanup_all_backups()

        except Exception as e:
            logger.error("Error during rollback", extra={"error": str(e)})
            rollback_results["success"] = False
            rollback_results["error"] = str(e)

        return rollback_results

    def cleanup_successful_conversions(self) -> Dict[str, Any]:
        """
        Clean up backups for successful conversions.

        Returns:
            Dict containing cleanup results
        """
        logger.info("Cleaning up backups for successful conversions")

        cleanup_results = {
            "success": True,
            "cleaned_backups": [],
            "failed_cleanups": []
        }

        successful_results = [
            result for result in self.results.values()
            if result.status == ProcessingStatus.COMPLETED and result.backup_id
        ]

        for result in successful_results:
            try:
                if self.fixture_manager.cleanup_backup(result.backup_id):
                    cleanup_results["cleaned_backups"].append(result.backup_id)
                    if result.backup_id in self.active_backups:
                        self.active_backups.remove(result.backup_id)
                else:
                    cleanup_results["failed_cleanups"].append(result.backup_id)
            except Exception as e:
                cleanup_results["failed_cleanups"].append({
                    "backup_id": result.backup_id,
                    "error": str(e)
                })

        if cleanup_results["failed_cleanups"]:
            cleanup_results["success"] = False

        return cleanup_results

    def _reset_processing_state(self) -> None:
        """Reset processing state for new batch"""
        with self._processing_lock:
            self.progress = BatchProcessingProgress()
            self.results = {}
            self.active_backups = []
            self._stop_processing.clear()

    def _process_folders_sequential(self, bucket_name: str, folders: List,
                                  dry_run: bool) -> List[FolderProcessingResult]:
        """Process folders sequentially"""
        results = []

        for folder_analysis in folders:
            if self._stop_processing.is_set():
                break

            with self._processing_lock:
                self.progress.current_folder = folder_analysis.folder_path
                self.progress.in_progress = 1

            result = self._process_single_folder(bucket_name, folder_analysis, dry_run)
            results.append(result)

            with self._processing_lock:
                if result.status == ProcessingStatus.COMPLETED:
                    self.progress.completed += 1
                elif result.status == ProcessingStatus.FAILED:
                    self.progress.failed += 1
                elif result.status == ProcessingStatus.SKIPPED:
                    self.progress.skipped += 1

                self.progress.in_progress = 0

            # Call progress callback if set
            if self.progress_callback:
                self.progress_callback(self.get_processing_progress())

        return results

    def _process_folders_parallel(self, bucket_name: str, folders: List,
                                max_workers: int) -> List[FolderProcessingResult]:
        """Process folders in parallel"""
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_folder = {
                executor.submit(self._process_single_folder, bucket_name, folder_analysis, False): folder_analysis
                for folder_analysis in folders
            }

            # Process completed jobs
            for future in as_completed(future_to_folder):
                if self._stop_processing.is_set():
                    # Cancel remaining futures
                    for f in future_to_folder:
                        if not f.done():
                            f.cancel()
                    break

                folder_analysis = future_to_folder[future]
                try:
                    result = future.result()
                    results.append(result)

                    with self._processing_lock:
                        if result.status == ProcessingStatus.COMPLETED:
                            self.progress.completed += 1
                        elif result.status == ProcessingStatus.FAILED:
                            self.progress.failed += 1
                        elif result.status == ProcessingStatus.SKIPPED:
                            self.progress.skipped += 1

                    # Call progress callback if set
                    if self.progress_callback:
                        self.progress_callback(self.get_processing_progress())

                except Exception as e:
                    logger.error("Error processing folder", extra={"folder_path": folder_analysis.folder_path, "error": str(e)})
                    result = FolderProcessingResult(
                        folder_path=folder_analysis.folder_path,
                        status=ProcessingStatus.FAILED,
                        error_message=str(e)
                    )
                    results.append(result)

        return results

    def _process_single_folder(self, bucket_name: str, folder_analysis,
                             dry_run: bool) -> FolderProcessingResult:
        """Process a single folder for OCFL conversion"""
        result = FolderProcessingResult(
            folder_path=folder_analysis.folder_path,
            status=ProcessingStatus.IN_PROGRESS,
            start_time=time.time()
        )

        try:
            logger.info("Processing folder", extra={"folder_path": folder_analysis.folder_path})

            # Skip if already OCFL compliant
            if folder_analysis.structure_type == StructureType.FULL_OCFL:
                result.status = ProcessingStatus.SKIPPED
                result.conversion_details["reason"] = "Already OCFL compliant"
                logger.info("Skipping folder - already OCFL compliant", extra={"folder_path": folder_analysis.folder_path})
                return result

            if dry_run:
                # For dry run, just simulate the process
                result.status = ProcessingStatus.COMPLETED
                result.conversion_details = {
                    "dry_run": True,
                    "would_convert": True,
                    "structure_type": folder_analysis.structure_type.value
                }
                logger.info("Dry run: would convert folder", extra={"folder_path": folder_analysis.folder_path})
                return result

            # Create backup before conversion
            try:
                backup_id = self.fixture_manager.create_fixture_backup(
                    bucket_name, folder_analysis.folder_path
                )
                result.backup_id = backup_id
                self.active_backups.append(backup_id)
                logger.debug("Created backup for folder", extra={"backup_id": backup_id, "folder_path": folder_analysis.folder_path})
            except Exception as e:
                logger.warning("Failed to create backup for folder", extra={"folder_path": folder_analysis.folder_path, "error": str(e)})
                # Continue without backup (risky but allows processing)

            # Perform conversion using enhanced OCFL service
            if hasattr(self.ocfl_service, 'convert_bundle_to_ocfl'):
                # Use bundle-focused conversion method
                conversion_result = self.ocfl_service.convert_bundle_to_ocfl(
                    bucket_name, folder_analysis.folder_path
                )
            else:
                # Fallback to existing transformation method
                conversion_result = self.ocfl_service.transform_structure(folder_analysis.folder_path)

            if conversion_result["success"]:
                result.status = ProcessingStatus.COMPLETED
                result.conversion_details = conversion_result
                result.files_processed = conversion_result.get("files_processed", 0)
                logger.info("Successfully converted folder", extra={"folder_path": folder_analysis.folder_path})
            else:
                result.status = ProcessingStatus.FAILED
                result.error_message = conversion_result.get("error", "Unknown conversion error")
                result.conversion_details = conversion_result
                logger.error("Failed to convert folder", extra={"folder_path": folder_analysis.folder_path, "error": result.error_message})

        except Exception as e:
            result.status = ProcessingStatus.FAILED
            result.error_message = str(e)
            logger.error("Exception processing folder", extra={"folder_path": folder_analysis.folder_path, "error": str(e)})

        finally:
            result.end_time = time.time()
            self.results[folder_analysis.folder_path] = result

        return result

    def _compile_final_results(self, analysis: BucketAnalysis, feasibility: Dict,
                             processing_results: List[FolderProcessingResult]) -> Dict[str, Any]:
        """Compile final processing results"""
        final_results = {
            "success": True,
            "bucket_name": analysis.bucket_name,
            "analysis": analysis,
            "feasibility": feasibility,
            "processing_summary": {
                "total_folders": self.progress.total_folders,
                "completed": self.progress.completed,
                "failed": self.progress.failed,
                "skipped": self.progress.skipped,
                "processing_time": time.time() - self.progress.start_time if self.progress.start_time else 0
            },
            "folder_results": [
                {
                    "folder_path": result.folder_path,
                    "status": result.status.value,
                    "processing_time": (result.end_time - result.start_time) if result.start_time and result.end_time else 0,
                    "files_processed": result.files_processed,
                    "error_message": result.error_message,
                    "has_backup": result.backup_id is not None
                }
                for result in processing_results
            ],
            "active_backups": len(self.active_backups),
            "recommendations": []
        }

        # Set overall success based on results
        if self.progress.failed > 0:
            final_results["success"] = False
            final_results["recommendations"].append("Some conversions failed - review errors and consider rollback")

        if self.progress.failed == 0 and self.progress.completed > 0:
            final_results["recommendations"].append("All conversions successful - consider cleaning up backups")

        if self.progress.skipped > 0:
            final_results["recommendations"].append(f"{self.progress.skipped} folders were already OCFL compliant")

        return final_results

    def _cleanup_all_backups(self) -> None:
        """Clean up all active backups"""
        for backup_id in self.active_backups[:]:  # Copy list to avoid modification during iteration
            try:
                self.fixture_manager.cleanup_backup(backup_id)
                self.active_backups.remove(backup_id)
            except Exception as e:
                logger.warning("Failed to cleanup backup", extra={"backup_id": backup_id, "error": str(e)})

    def set_progress_callback(self, callback: Callable[[BatchProcessingProgress], None]) -> None:
        """
        Set callback function for progress updates.

        Args:
            callback: Function to call with progress updates
        """
        self.progress_callback = callback
