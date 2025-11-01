#!/usr/bin/env python
import json
import yaml
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from lacos.storage.services.registry import get_bucket_service
from lacos.storage.services.bucket_structure_scanner import BucketStructureScanner


class Command(BaseCommand):
    help = 'Scan bucket structures and analyze OCFL conversion feasibility'

    def add_arguments(self, parser):
        parser.add_argument('bucket_name', type=str, help='Name of bucket to scan')
        parser.add_argument(
            '--output-format',
            choices=['json', 'yaml', 'text'],
            default='text',
            help='Output format for analysis results'
        )
        parser.add_argument(
            '--output-file',
            type=str,
            help='File to write analysis results to (default: stdout)'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Include detailed analysis of each folder'
        )

    def handle(self, *args, **options):
        bucket_name = options['bucket_name']
        output_format = options['output_format']
        output_file = options.get('output_file')
        detailed = options.get('detailed', False)

        try:
            # Initialize services
            bucket_service = get_bucket_service()
            scanner = BucketStructureScanner(bucket_service)

            if output_format == 'text' and not output_file:
                self.stdout.write(f"Scanning bucket structures for: {bucket_name}")

            # Perform bucket analysis
            analysis = scanner.scan_bucket_structures(bucket_name)

            # Generate output based on format
            if output_format == 'json':
                output_data = self._format_json_output(analysis, detailed)
                output_content = json.dumps(output_data, indent=2, default=str)
            elif output_format == 'yaml':
                output_data = self._format_json_output(analysis, detailed)
                output_content = yaml.dump(output_data, default_flow_style=False)
            else:
                output_content = self._format_text_output(analysis, detailed)

            # Write output
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(output_content)
                self.stdout.write(
                    self.style.SUCCESS(f"Analysis written to {output_file}")
                )
            else:
                self.stdout.write(output_content)

        except Exception as e:
            raise CommandError(f"Error scanning bucket {bucket_name}: {str(e)}")

    def _format_json_output(self, analysis, detailed):
        """Format analysis as JSON/YAML compatible data"""
        output = {
            "bucket_name": analysis.bucket_name,
            "total_folders": analysis.total_folders,
            "total_files": analysis.total_files,
            "total_size": analysis.total_size,
            "conversion_feasibility": analysis.conversion_feasibility,
            "estimated_conversion_time": analysis.estimated_conversion_time,
            "structure_breakdown": {
                structure_type.value: count
                for structure_type, count in analysis.structure_breakdown.items()
            },
            "blocking_issues": analysis.blocking_issues,
            "recommendations": analysis.recommendations
        }

        if detailed:
            output["folders"] = [
                {
                    "folder_path": folder.folder_path,
                    "structure_type": folder.structure_type.value,
                    "conversion_complexity": folder.conversion_complexity,
                    "total_files": folder.total_files,
                    "total_size": folder.total_size,
                    "has_ocfl_marker": folder.has_ocfl_marker,
                    "has_version_directory": folder.has_version_directory,
                    "has_content_directory": folder.has_content_directory,
                    "has_metadata_files": folder.has_metadata_files,
                    "has_data_directory": folder.has_data_directory,
                    "has_acl_file": folder.has_acl_file,
                    "xml_files": folder.xml_files,
                    "preservation_requirements": folder.preservation_requirements,
                    "issues": folder.issues,
                    "recommendations": folder.recommendations
                }
                for folder in analysis.folders
            ]

        return output

    def _format_text_output(self, analysis, detailed):
        """Format analysis as human-readable text"""
        output_lines = []
        output_lines.append(f"Bucket Structure Analysis: {analysis.bucket_name}")
        output_lines.append("=" * 50)
        output_lines.append("")

        # Summary statistics
        output_lines.append("Summary:")
        output_lines.append(f"  Total folders: {analysis.total_folders}")
        output_lines.append(f"  Total files: {analysis.total_files}")
        output_lines.append(f"  Total size: {self._format_size(analysis.total_size)}")
        output_lines.append(f"  Conversion feasibility: {analysis.conversion_feasibility}")
        output_lines.append(f"  Estimated conversion time: {analysis.estimated_conversion_time}")
        output_lines.append("")

        # Structure breakdown
        output_lines.append("Structure Types:")
        for structure_type, count in analysis.structure_breakdown.items():
            if count > 0:
                percentage = (count / analysis.total_folders) * 100 if analysis.total_folders > 0 else 0
                output_lines.append(f"  {structure_type.value}: {count} ({percentage:.1f}%)")
        output_lines.append("")

        # Blocking issues
        if analysis.blocking_issues:
            output_lines.append("Blocking Issues:")
            for issue in analysis.blocking_issues:
                output_lines.append(f"  • {issue}")
            output_lines.append("")

        # Recommendations
        if analysis.recommendations:
            output_lines.append("Recommendations:")
            for recommendation in analysis.recommendations:
                output_lines.append(f"  • {recommendation}")
            output_lines.append("")

        # Detailed folder analysis
        if detailed and analysis.folders:
            output_lines.append("Detailed Folder Analysis:")
            output_lines.append("-" * 40)

            for folder in analysis.folders:
                output_lines.append(f"\nFolder: {folder.folder_path}")
                output_lines.append(f"  Structure type: {folder.structure_type.value}")
                output_lines.append(f"  Conversion complexity: {folder.conversion_complexity}")
                output_lines.append(f"  Files: {folder.total_files} ({self._format_size(folder.total_size)})")

                # OCFL status
                ocfl_status = []
                if folder.has_ocfl_marker:
                    ocfl_status.append("OCFL marker")
                if folder.has_version_directory:
                    ocfl_status.append("version directory")
                if folder.has_content_directory:
                    ocfl_status.append("content directory")

                if ocfl_status:
                    output_lines.append(f"  OCFL components: {', '.join(ocfl_status)}")

                # Content
                content_items = []
                if folder.has_metadata_files:
                    content_items.append(f"{len(folder.xml_files)} XML files")
                if folder.has_data_directory:
                    content_items.append("data directory")
                if folder.has_acl_file:
                    content_items.append("ACL file")

                if content_items:
                    output_lines.append(f"  Content: {', '.join(content_items)}")

                # Issues and recommendations
                if folder.issues:
                    output_lines.append(f"  Issues: {'; '.join(folder.issues)}")

                if folder.recommendations:
                    output_lines.append(f"  Recommendations: {'; '.join(folder.recommendations)}")

        return "\n".join(output_lines)

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
