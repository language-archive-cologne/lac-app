#!/usr/bin/env python
import json
import time
import threading
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from lacos.storage.services.registry import get_bucket_service
from lacos.storage.services.ocfl_service import OCFLService
from lacos.storage.services.bucket_ocfl_processor import BucketOCFLProcessor


class Command(BaseCommand):
    help = 'Process all collections for OCFL conversion with batch operations'

    def add_arguments(self, parser):
        parser.add_argument('bucket_name', type=str, help='Name of bucket to process')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Analyze and plan without making changes'
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Process collections in parallel (faster but more resource intensive)'
        )
        parser.add_argument(
            '--max-workers',
            type=int,
            default=3,
            help='Maximum number of parallel workers (default: 3)'
        )
        parser.add_argument(
            '--output-format',
            choices=['text', 'json'],
            default='text',
            help='Output format for results'
        )
        parser.add_argument(
            '--progress',
            action='store_true',
            help='Show real-time progress updates'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force processing even if feasibility check fails'
        )

    def handle(self, *args, **options):
        bucket_name = options['bucket_name']
        dry_run = options.get('dry_run', False)
        parallel = options.get('parallel', False)
        max_workers = options.get('max_workers', 3)
        output_format = options.get('output_format', 'text')
        show_progress = options.get('progress', False)
        force = options.get('force', False)

        try:
            # Initialize services
            bucket_service = get_bucket_service()
            ocfl_service = OCFLService(bucket_service)
            processor = BucketOCFLProcessor(bucket_service, ocfl_service)

            if output_format == 'text':
                self.stdout.write(f"Processing collections in bucket {bucket_name} for OCFL conversion")
                self.stdout.write(f"Mode: {'Dry run' if dry_run else 'Live conversion'}")
                self.stdout.write(f"Parallel processing: {parallel}")
                if parallel:
                    self.stdout.write(f"Max workers: {max_workers}")
                self.stdout.write("")

            # Set up progress callback if requested
            if show_progress and output_format == 'text':
                progress_thread = threading.Thread(
                    target=self._progress_monitor,
                    args=(processor,),
                    daemon=True
                )
                progress_thread.start()

            # Perform bucket processing
            start_time = time.time()
            results = processor.process_all_collections(
                bucket_name=bucket_name,
                dry_run=dry_run,
                parallel=parallel,
                max_workers=max_workers
            )

            processing_time = time.time() - start_time

            # Display results
            if output_format == 'text':
                self._display_results_text(results, processing_time, dry_run)
            else:
                results["processing_time"] = processing_time
                self.stdout.write(json.dumps(results, indent=2, default=str))

            # Handle post-processing actions
            if not dry_run and results["success"]:
                self._handle_post_processing(processor, results, output_format)

        except KeyboardInterrupt:
            if output_format == 'text':
                self.stdout.write(self.style.WARNING("\nProcessing interrupted by user"))
            if 'processor' in locals():
                processor.stop_processing()
        except Exception as e:
            raise CommandError(f"Error processing bucket {bucket_name}: {str(e)}")

    def _progress_monitor(self, processor):
        """Monitor and display processing progress"""
        try:
            while True:
                progress = processor.get_processing_progress()

                if progress.total_folders > 0:
                    percentage = ((progress.completed + progress.failed + progress.skipped) / progress.total_folders) * 100
                    self.stdout.write(
                        f"\rProgress: {percentage:.1f}% "
                        f"({progress.completed} collections completed, {progress.failed} failed, "
                        f"{progress.skipped} skipped, {progress.in_progress} in progress)",
                        ending=""
                    )
                    self.stdout.flush()

                    # Show current collection
                    if progress.current_folder:
                        self.stdout.write(f" - Processing collection: {progress.current_folder}", ending="")

                    # Stop monitoring when processing is complete
                    if (progress.completed + progress.failed + progress.skipped) >= progress.total_folders:
                        self.stdout.write("")  # New line
                        break

                time.sleep(2)  # Update every 2 seconds

        except Exception:
            pass  # Silently handle monitoring errors

    def _display_results_text(self, results, processing_time, dry_run):
        """Display results in text format"""
        if not results["success"]:
            self.stdout.write(self.style.ERROR(f"Processing failed: {results.get('error', 'Unknown error')}"))
            return

        summary = results["processing_summary"]

        self.stdout.write("")
        self.stdout.write("Processing Results:")
        self.stdout.write("=" * 40)
        self.stdout.write(f"Total collections: {summary['total_folders']}")
        self.stdout.write(f"Completed: {summary['completed']}")
        self.stdout.write(f"Failed: {summary['failed']}")
        self.stdout.write(f"Skipped: {summary['skipped']}")
        self.stdout.write(f"Processing time: {processing_time:.1f} seconds")

        if dry_run:
            self.stdout.write("")
            self.stdout.write("DRY RUN - No changes were made")

        # Show analysis summary
        if "analysis" in results:
            analysis = results["analysis"]
            self.stdout.write("")
            self.stdout.write("Bucket Analysis:")
            self.stdout.write(f"  Conversion feasibility: {analysis.conversion_feasibility}")
            self.stdout.write(f"  Estimated time: {analysis.estimated_conversion_time}")

            # Structure breakdown
            if analysis.structure_breakdown:
                self.stdout.write("  Structure types:")
                for structure_type, count in analysis.structure_breakdown.items():
                    if count > 0:
                        percentage = (count / analysis.total_folders) * 100 if analysis.total_folders > 0 else 0
                        self.stdout.write(f"    {structure_type.value}: {count} ({percentage:.1f}%)")

        # Show failed collections
        failed_collections = [f for f in results["folder_results"] if f["status"] == "failed"]
        if failed_collections:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Failed conversions:"))
            for collection in failed_collections:
                self.stdout.write(f"  • {collection['folder_path']}: {collection['error_message']}")

        # Show recommendations
        if results.get("recommendations"):
            self.stdout.write("")
            self.stdout.write("Recommendations:")
            for recommendation in results["recommendations"]:
                self.stdout.write(f"  • {recommendation}")

        # Show active backups
        if results.get("active_backups", 0) > 0:
            self.stdout.write("")
            self.stdout.write(f"Active backups: {results['active_backups']}")
            self.stdout.write("Use 'python manage.py cleanup_ocfl_backups' to clean up successful conversions")

    def _handle_post_processing(self, processor, results, output_format):
        """Handle post-processing actions"""
        summary = results["processing_summary"]

        # If there are failures, ask about rollback
        if summary["failed"] > 0:
            if output_format == 'text':
                self.stdout.write("")
                response = input("Some conversions failed. Do you want to rollback all changes? (y/N): ")

                if response.lower() in ['y', 'yes']:
                    self.stdout.write("Rolling back failed conversions...")
                    rollback_result = processor.rollback_failed_conversions(results["bucket_name"])

                    if rollback_result["success"]:
                        self.stdout.write(self.style.SUCCESS("Rollback completed successfully"))
                        if rollback_result["restored_folders"]:
                            self.stdout.write(f"Restored {len(rollback_result['restored_folders'])} collections")
                    else:
                        self.stdout.write(self.style.ERROR("Rollback failed"))
                        if rollback_result.get("failed_rollbacks"):
                            for failure in rollback_result["failed_rollbacks"]:
                                self.stdout.write(f"  Failed to rollback: {failure}")

        # If all conversions succeeded, offer to clean up backups
        elif summary["completed"] > 0 and results.get("active_backups", 0) > 0:
            if output_format == 'text':
                self.stdout.write("")
                response = input("All conversions succeeded. Clean up backups? (Y/n): ")

                if response.lower() not in ['n', 'no']:
                    self.stdout.write("Cleaning up backups...")
                    cleanup_result = processor.cleanup_successful_conversions()

                    if cleanup_result["success"]:
                        self.stdout.write(self.style.SUCCESS("Backup cleanup completed"))
                        if cleanup_result["cleaned_backups"]:
                            self.stdout.write(f"Cleaned up {len(cleanup_result['cleaned_backups'])} backups")
                    else:
                        self.stdout.write(self.style.WARNING("Some backups could not be cleaned up"))
                        if cleanup_result.get("failed_cleanups"):
                            for failure in cleanup_result["failed_cleanups"]:
                                self.stdout.write(f"  Failed to clean: {failure}")

class ProgressCallback:
    """Callback class for progress updates"""

    def __init__(self, command):
        self.command = command
        self.last_update = 0

    def __call__(self, progress):
        # Only update every 2 seconds to avoid spam
        current_time = time.time()
        if current_time - self.last_update < 2:
            return

        self.last_update = current_time

        if progress.total_folders > 0:
            percentage = ((progress.completed + progress.failed + progress.skipped) / progress.total_folders) * 100
            self.command.stdout.write(
                f"\rProgress: {percentage:.1f}% "
                f"({progress.completed} completed, {progress.failed} failed, "
                f"{progress.skipped} skipped)",
                ending=""
            )
            self.command.stdout.flush()
