#!/usr/bin/env python
import json
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from lacos.storage.services.registry import get_bucket_service
from lacos.storage.services.ocfl_service import OCFLService
from lacos.storage.services.ocfl_fixture_manager import OCFLFixtureManager


class Command(BaseCommand):
    help = 'Convert a single bundle to OCFL format in-place within the same bucket'

    def add_arguments(self, parser):
        parser.add_argument('bucket_name', type=str, help='Name of bucket containing the bundle')
        parser.add_argument('bundle_path', type=str, help='Path to the bundle to convert')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force conversion even if risks are detected'
        )
        parser.add_argument(
            '--backup',
            action='store_true',
            help='Create backup before conversion (recommended)'
        )
        parser.add_argument(
            '--output-format',
            choices=['text', 'json'],
            default='text',
            help='Output format for results'
        )

    def handle(self, *args, **options):
        bucket_name = options['bucket_name']
        bundle_path = options['bundle_path']
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        create_backup = options.get('backup', False)
        output_format = options.get('output_format', 'text')

        try:
            # Initialize services
            bucket_service = get_bucket_service()
            ocfl_service = OCFLService(bucket_service)
            fixture_manager = OCFLFixtureManager(bucket_service)

            if output_format == 'text':
                self.stdout.write(f"Converting bundle to OCFL: {bundle_path}")
                self.stdout.write(f"Bucket: {bucket_name}")
                self.stdout.write(f"Dry run: {dry_run}")
                self.stdout.write("")

            # First, analyze the bundle structure
            analysis_result = ocfl_service.analyze_folder_structure(bucket_name, bundle_path)

            if not analysis_result["success"]:
                raise CommandError(f"Failed to analyze bundle: {analysis_result['error']}")

            structure = analysis_result["structure_analysis"]

            # Check if already OCFL compliant
            if structure["is_ocfl_compliant"]:
                message = f"Bundle {bundle_path} is already OCFL compliant"
                if output_format == 'text':
                    self.stdout.write(self.style.SUCCESS(message))
                else:
                    self.stdout.write(json.dumps({
                        "success": True,
                        "message": message,
                        "needs_conversion": False
                    }))
                return

            # Create conversion plan
            conversion_plan = ocfl_service.create_conversion_plan(analysis_result)

            if output_format == 'text':
                self._display_analysis_text(analysis_result, conversion_plan)
            else:
                self._display_analysis_json(analysis_result, conversion_plan)

            # Check feasibility
            if not conversion_plan["feasible"]:
                error_msg = f"Conversion not feasible: {', '.join(conversion_plan['risks'])}"
                if not force:
                    raise CommandError(error_msg + " (use --force to override)")
                else:
                    if output_format == 'text':
                        self.stdout.write(self.style.WARNING(f"Forcing conversion despite risks: {error_msg}"))

            # Check for risks
            if conversion_plan["risks"] and not force:
                if output_format == 'text':
                    self.stdout.write(self.style.WARNING("Risks detected:"))
                    for risk in conversion_plan["risks"]:
                        self.stdout.write(f"  • {risk}")
                    self.stdout.write("Use --force to proceed anyway")
                return

            # If dry run, show what would be done
            if dry_run:
                if output_format == 'text':
                    self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))
                    self.stdout.write("Conversion steps that would be performed:")
                    for i, step in enumerate(conversion_plan["steps"], 1):
                        self.stdout.write(f"  {i}. {step}")

                    if conversion_plan["preserve_items"]:
                        self.stdout.write("Items that would be preserved:")
                        for item in conversion_plan["preserve_items"]:
                            self.stdout.write(f"  • {item}")
                else:
                    self.stdout.write(json.dumps({
                        "success": True,
                        "dry_run": True,
                        "conversion_plan": conversion_plan,
                        "analysis": analysis_result
                    }))
                return

            # Create backup if requested
            backup_id = None
            if create_backup:
                try:
                    backup_id = fixture_manager.create_fixture_backup(bucket_name, bundle_path)
                    if output_format == 'text':
                        self.stdout.write(f"Created backup: {backup_id}")
                except Exception as e:
                    if output_format == 'text':
                        self.stdout.write(self.style.WARNING(f"Failed to create backup: {str(e)}"))
                    if not force:
                        raise CommandError("Backup creation failed (use --force to proceed without backup)")

            # Perform conversion
            if output_format == 'text':
                self.stdout.write("Starting conversion...")

            conversion_result = ocfl_service.convert_bundle_to_ocfl(bucket_name, bundle_path)

            # Display results
            if output_format == 'text':
                if conversion_result["success"]:
                    self.stdout.write(self.style.SUCCESS("Conversion completed successfully!"))
                    self.stdout.write(f"Conversion type: {conversion_result.get('conversion_type', 'unknown')}")
                    self.stdout.write(f"Files processed: {conversion_result.get('files_processed', 0)}")

                    if conversion_result.get('preserved_items'):
                        self.stdout.write("Preserved items:")
                        for item in conversion_result['preserved_items']:
                            self.stdout.write(f"  • {item}")

                    if backup_id:
                        self.stdout.write(f"Backup created: {backup_id}")
                        self.stdout.write("Use 'python manage.py cleanup_ocfl_backups' to clean up successful conversions")
                else:
                    self.stdout.write(self.style.ERROR(f"Conversion failed: {conversion_result['error']}"))
                    if backup_id:
                        self.stdout.write(f"Backup available for rollback: {backup_id}")
            else:
                output_result = conversion_result.copy()
                if backup_id:
                    output_result["backup_id"] = backup_id
                self.stdout.write(json.dumps(output_result, indent=2))

        except Exception as e:
            raise CommandError(f"Error converting bundle {bundle_path}: {str(e)}")

    def _display_analysis_text(self, analysis_result, conversion_plan):
        """Display analysis results in text format"""
        structure = analysis_result["structure_analysis"]

        self.stdout.write("Bundle Analysis:")
        self.stdout.write(f"  Total files: {structure['total_files']}")
        self.stdout.write(f"  Total size: {self._format_size(structure['total_size'])}")

        # OCFL status
        ocfl_components = []
        if structure["has_ocfl_marker"]:
            ocfl_components.append("OCFL marker")
        if structure["has_version_directory"]:
            ocfl_components.append("version directory")
        if structure["has_content_directory"]:
            ocfl_components.append("content directory")

        if ocfl_components:
            self.stdout.write(f"  Existing OCFL components: {', '.join(ocfl_components)}")

        # Content
        content_items = []
        if structure["has_metadata_files"]:
            content_items.append(f"{len(structure['xml_files'])} XML files")
        if structure.get("has_data_directory"):
            content_items.append("data directory")
        if structure["has_acl_file"]:
            content_items.append("ACL file")

        if content_items:
            self.stdout.write(f"  Content: {', '.join(content_items)}")

        self.stdout.write("")

        # Conversion plan
        self.stdout.write("Conversion Plan:")
        self.stdout.write(f"  Type: {conversion_plan['conversion_type']}")
        self.stdout.write(f"  Estimated time: {conversion_plan['estimated_time']}")

        if conversion_plan["steps"]:
            self.stdout.write("  Steps:")
            for step in conversion_plan["steps"]:
                self.stdout.write(f"    • {step}")

        if conversion_plan["preserve_items"]:
            self.stdout.write("  Items to preserve:")
            for item in conversion_plan["preserve_items"]:
                self.stdout.write(f"    • {item}")

        if conversion_plan["risks"]:
            self.stdout.write("  Risks:")
            for risk in conversion_plan["risks"]:
                self.stdout.write(f"    • {risk}")

        self.stdout.write("")

    def _display_analysis_json(self, analysis_result, conversion_plan):
        """Display analysis results in JSON format"""
        output = {
            "analysis": analysis_result,
            "conversion_plan": conversion_plan
        }
        self.stdout.write(json.dumps(output, indent=2, default=str))

    def _format_size(self, size_bytes):
        """Format size in bytes to human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
