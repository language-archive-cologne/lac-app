#!/usr/bin/env python
import json
import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.ocfl_service import OCFLService
from lacos.storage.services.bucket_structure_scanner import BucketStructureScanner, StructureType


class Command(BaseCommand):
    help = 'Validate OCFL structures in a bucket and generate compliance report'

    def add_arguments(self, parser):
        parser.add_argument('bucket_name', type=str, help='Name of bucket to validate')
        parser.add_argument(
            '--report-path',
            type=str,
            help='Path to write detailed validation report'
        )
        parser.add_argument(
            '--output-format',
            choices=['text', 'json'],
            default='text',
            help='Output format for results'
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Use strict OCFL validation (fail on any non-compliance)'
        )
        parser.add_argument(
            '--check-content',
            action='store_true',
            help='Validate content structure in addition to OCFL markers'
        )

    def handle(self, *args, **options):
        bucket_name = options['bucket_name']
        report_path = options.get('report_path')
        output_format = options.get('output_format', 'text')
        strict = options.get('strict', False)
        check_content = options.get('check_content', False)

        try:
            # Initialize services
            bucket_service = BucketService()
            ocfl_service = OCFLService(bucket_service)
            scanner = BucketStructureScanner(bucket_service)

            if output_format == 'text':
                self.stdout.write(f"Validating OCFL structures in bucket: {bucket_name}")
                self.stdout.write(f"Strict mode: {strict}")
                self.stdout.write(f"Content validation: {check_content}")
                self.stdout.write("")

            # Scan bucket structures
            analysis = scanner.scan_bucket_structures(bucket_name)

            # Perform validation
            validation_results = self._validate_bucket_ocfl(
                bucket_service, ocfl_service, analysis, strict, check_content
            )

            # Generate report
            report = self._generate_validation_report(analysis, validation_results, strict)

            # Display results
            if output_format == 'text':
                self._display_results_text(report)
            else:
                self.stdout.write(json.dumps(report, indent=2, default=str))

            # Write detailed report if requested
            if report_path:
                self._write_detailed_report(report, report_path)
                if output_format == 'text':
                    self.stdout.write(f"\nDetailed report written to: {report_path}")

        except Exception as e:
            raise CommandError(f"Error validating bucket {bucket_name}: {str(e)}")

    def _validate_bucket_ocfl(self, bucket_service, ocfl_service, analysis, strict, check_content):
        """Validate OCFL structures in the bucket"""
        validation_results = {
            "total_folders": analysis.total_folders,
            "compliant_folders": 0,
            "non_compliant_folders": 0,
            "partial_ocfl_folders": 0,
            "validation_errors": [],
            "folder_validations": []
        }

        for folder in analysis.folders:
            folder_validation = {
                "folder_path": folder.folder_path,
                "structure_type": folder.structure_type.value,
                "is_compliant": False,
                "issues": [],
                "warnings": [],
                "content_validation": None
            }

            # Check OCFL compliance
            if folder.structure_type == StructureType.FULL_OCFL:
                folder_validation["is_compliant"] = True
                validation_results["compliant_folders"] += 1

                # Additional content validation if requested
                if check_content:
                    content_validation = self._validate_ocfl_content(
                        bucket_service, folder.folder_path
                    )
                    folder_validation["content_validation"] = content_validation

                    if not content_validation["valid"] and strict:
                        folder_validation["is_compliant"] = False
                        folder_validation["issues"].extend(content_validation["issues"])

            elif folder.structure_type == StructureType.PARTIAL_OCFL:
                validation_results["partial_ocfl_folders"] += 1
                folder_validation["issues"].append("Incomplete OCFL structure")

                if not strict:
                    folder_validation["warnings"].append("Partial OCFL structure detected")
                else:
                    folder_validation["issues"].append("Strict mode: partial OCFL not acceptable")

            else:
                validation_results["non_compliant_folders"] += 1
                folder_validation["issues"].append(f"Non-OCFL structure: {folder.structure_type.value}")

            # Additional checks
            if folder.issues:
                folder_validation["issues"].extend(folder.issues)

            # Add folder validation to results
            validation_results["folder_validations"].append(folder_validation)

        return validation_results

    def _validate_ocfl_content(self, bucket_service, folder_path):
        """Validate content structure of an OCFL folder"""
        content_validation = {
            "valid": True,
            "issues": [],
            "warnings": []
        }

        try:
            # Check for required directories
            required_paths = [
                f"{folder_path}/v1",
                f"{folder_path}/v1/content"
            ]

            for required_path in required_paths:
                contents = bucket_service.list_bucket_contents(bucket_service.ingest_bucket, required_path)
                if not contents:
                    content_validation["valid"] = False
                    content_validation["issues"].append(f"Missing required directory: {required_path}")

            # Check for metadata directory
            metadata_path = f"{folder_path}/v1/content/metadata"
            metadata_contents = bucket_service.list_bucket_contents(bucket_service.ingest_bucket, metadata_path)

            if metadata_contents:
                # Validate metadata files
                xml_files = [item for item in metadata_contents if item["name"].endswith(".xml")]
                if not xml_files:
                    content_validation["warnings"].append("No XML metadata files found")

                # Check for ACL file
                acl_files = [item for item in metadata_contents if item["name"] == "acl.json"]
                if not acl_files:
                    content_validation["warnings"].append("No ACL file found")
            else:
                content_validation["warnings"].append("No metadata directory found")

            # Check for Resources directory
            resources_path = f"{folder_path}/v1/content/Resources"
            resources_contents = bucket_service.list_bucket_contents(bucket_service.ingest_bucket, resources_path)

            if not resources_contents:
                content_validation["warnings"].append("No Resources directory found")

        except Exception as e:
            content_validation["valid"] = False
            content_validation["issues"].append(f"Content validation error: {str(e)}")

        return content_validation

    def _generate_validation_report(self, analysis, validation_results, strict):
        """Generate comprehensive validation report"""
        total_folders = validation_results["total_folders"]
        compliant = validation_results["compliant_folders"]
        non_compliant = validation_results["non_compliant_folders"]
        partial = validation_results["partial_ocfl_folders"]

        # Calculate compliance percentage
        if strict:
            compliance_percentage = (compliant / total_folders) * 100 if total_folders > 0 else 0
        else:
            # In non-strict mode, partial OCFL counts as partial compliance
            compliance_percentage = ((compliant + partial * 0.5) / total_folders) * 100 if total_folders > 0 else 0

        report = {
            "bucket_name": analysis.bucket_name,
            "validation_timestamp": analysis.folders[0].preservation_requirements if analysis.folders else None,
            "strict_mode": strict,
            "overall_compliance": {
                "total_folders": total_folders,
                "compliant_folders": compliant,
                "non_compliant_folders": non_compliant,
                "partial_ocfl_folders": partial,
                "compliance_percentage": round(compliance_percentage, 2)
            },
            "validation_summary": {
                "passes_validation": compliance_percentage >= 100 if strict else compliance_percentage >= 80,
                "issues_found": len([f for f in validation_results["folder_validations"] if f["issues"]]),
                "warnings_found": len([f for f in validation_results["folder_validations"] if f["warnings"]])
            },
            "structure_breakdown": {
                structure_type.value: count
                for structure_type, count in analysis.structure_breakdown.items()
            },
            "folder_details": validation_results["folder_validations"],
            "recommendations": self._generate_recommendations(validation_results, strict)
        }

        return report

    def _generate_recommendations(self, validation_results, strict):
        """Generate recommendations based on validation results"""
        recommendations = []

        compliant = validation_results["compliant_folders"]
        non_compliant = validation_results["non_compliant_folders"]
        partial = validation_results["partial_ocfl_folders"]
        total = validation_results["total_folders"]

        if total == 0:
            recommendations.append("Empty bucket - no action needed")
            return recommendations

        compliance_rate = (compliant / total) * 100

        if compliance_rate == 100:
            recommendations.append("All folders are OCFL compliant")
            recommendations.append("Consider regular validation to maintain compliance")
        elif compliance_rate >= 80:
            recommendations.append("Good OCFL compliance rate")
            if partial > 0:
                recommendations.append(f"Complete {partial} partial OCFL structures")
            if non_compliant > 0:
                recommendations.append(f"Convert {non_compliant} non-compliant folders")
        elif compliance_rate >= 50:
            recommendations.append("Moderate OCFL compliance")
            recommendations.append("Consider batch conversion of non-compliant folders")
            recommendations.append("Use 'process_collections_ocfl' command for bulk conversion")
        else:
            recommendations.append("Low OCFL compliance rate")
            recommendations.append("Comprehensive conversion strategy needed")
            recommendations.append("Start with 'scan_bucket_structures' for detailed analysis")

        # Specific recommendations for issues
        folder_issues = [f for f in validation_results["folder_validations"] if f["issues"]]
        if folder_issues:
            recommendations.append(f"Address {len(folder_issues)} folders with validation issues")

        return recommendations

    def _display_results_text(self, report):
        """Display results in text format"""
        compliance = report["overall_compliance"]
        summary = report["validation_summary"]

        self.stdout.write("OCFL Validation Results:")
        self.stdout.write("=" * 40)
        self.stdout.write(f"Total folders: {compliance['total_folders']}")
        self.stdout.write(f"Compliant: {compliance['compliant_folders']}")
        self.stdout.write(f"Non-compliant: {compliance['non_compliant_folders']}")
        self.stdout.write(f"Partial OCFL: {compliance['partial_ocfl_folders']}")
        self.stdout.write(f"Compliance rate: {compliance['compliance_percentage']}%")
        self.stdout.write("")

        # Overall status
        if summary["passes_validation"]:
            self.stdout.write(self.style.SUCCESS("✓ Bucket passes OCFL validation"))
        else:
            self.stdout.write(self.style.ERROR("✗ Bucket fails OCFL validation"))

        # Issues and warnings
        if summary["issues_found"] > 0:
            self.stdout.write(self.style.ERROR(f"Issues found: {summary['issues_found']}"))

        if summary["warnings_found"] > 0:
            self.stdout.write(self.style.WARNING(f"Warnings found: {summary['warnings_found']}"))

        self.stdout.write("")

        # Structure breakdown
        self.stdout.write("Structure Breakdown:")
        for structure_type, count in report["structure_breakdown"].items():
            if count > 0:
                percentage = (count / compliance['total_folders']) * 100 if compliance['total_folders'] > 0 else 0
                self.stdout.write(f"  {structure_type}: {count} ({percentage:.1f}%)")

        self.stdout.write("")

        # Non-compliant folders
        non_compliant_folders = [f for f in report["folder_details"] if not f["is_compliant"]]
        if non_compliant_folders:
            self.stdout.write("Non-compliant folders:")
            for folder in non_compliant_folders[:10]:  # Show first 10
                self.stdout.write(f"  • {folder['folder_path']} ({folder['structure_type']})")
                if folder["issues"]:
                    for issue in folder["issues"][:2]:  # Show first 2 issues
                        self.stdout.write(f"    - {issue}")

            if len(non_compliant_folders) > 10:
                self.stdout.write(f"  ... and {len(non_compliant_folders) - 10} more")

            self.stdout.write("")

        # Recommendations
        if report["recommendations"]:
            self.stdout.write("Recommendations:")
            for recommendation in report["recommendations"]:
                self.stdout.write(f"  • {recommendation}")

    def _write_detailed_report(self, report, report_path):
        """Write detailed validation report to file"""
        try:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)

            if report_path.endswith('.json'):
                with open(report_path, 'w') as f:
                    json.dump(report, f, indent=2, default=str)
            else:
                # Write as text report
                with open(report_path, 'w') as f:
                    f.write("OCFL Bucket Validation Report\n")
                    f.write("=" * 50 + "\n\n")

                    # Summary
                    compliance = report["overall_compliance"]
                    f.write(f"Bucket: {report['bucket_name']}\n")
                    f.write(f"Validation Date: {report.get('validation_timestamp', 'Unknown')}\n")
                    f.write(f"Strict Mode: {report['strict_mode']}\n\n")

                    f.write("Summary:\n")
                    f.write(f"  Total folders: {compliance['total_folders']}\n")
                    f.write(f"  Compliant: {compliance['compliant_folders']}\n")
                    f.write(f"  Non-compliant: {compliance['non_compliant_folders']}\n")
                    f.write(f"  Partial OCFL: {compliance['partial_ocfl_folders']}\n")
                    f.write(f"  Compliance rate: {compliance['compliance_percentage']}%\n\n")

                    # Detailed folder results
                    f.write("Detailed Folder Validation:\n")
                    f.write("-" * 40 + "\n")

                    for folder in report["folder_details"]:
                        f.write(f"\nFolder: {folder['folder_path']}\n")
                        f.write(f"  Structure type: {folder['structure_type']}\n")
                        f.write(f"  Compliant: {folder['is_compliant']}\n")

                        if folder["issues"]:
                            f.write("  Issues:\n")
                            for issue in folder["issues"]:
                                f.write(f"    - {issue}\n")

                        if folder["warnings"]:
                            f.write("  Warnings:\n")
                            for warning in folder["warnings"]:
                                f.write(f"    - {warning}\n")

                        if folder.get("content_validation"):
                            cv = folder["content_validation"]
                            f.write(f"  Content validation: {'Valid' if cv['valid'] else 'Invalid'}\n")

                    # Recommendations
                    if report["recommendations"]:
                        f.write("\nRecommendations:\n")
                        for recommendation in report["recommendations"]:
                            f.write(f"  • {recommendation}\n")

        except Exception as e:
            raise CommandError(f"Failed to write report to {report_path}: {str(e)}")
