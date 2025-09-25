import logging
import os
from typing import Dict, Any, List, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class StructureType(Enum):
    """Types of folder structures detected in buckets"""
    FULL_OCFL = "full_ocfl"  # Complete OCFL structure with version marker and v1/content
    PARTIAL_OCFL = "partial_ocfl"  # Has some OCFL elements but incomplete
    LEGACY_STRUCTURED = "legacy_structured"  # Traditional structure with metadata + Resources
    LEGACY_FLAT = "legacy_flat"  # Flat structure without clear organization
    MIXED = "mixed"  # Contains both OCFL and non-OCFL elements
    UNKNOWN = "unknown"  # Cannot determine structure type


@dataclass
class FolderAnalysis:
    """Analysis result for a single folder"""
    folder_path: str
    structure_type: StructureType
    has_ocfl_marker: bool = False
    has_version_directory: bool = False
    has_content_directory: bool = False
    has_metadata_files: bool = False
    has_resources_directory: bool = False
    has_acl_file: bool = False
    xml_files: List[str] = field(default_factory=list)
    total_files: int = 0
    total_size: int = 0
    conversion_complexity: str = "low"  # low, medium, high
    preservation_requirements: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class BucketAnalysis:
    """Analysis result for an entire bucket"""
    bucket_name: str
    total_folders: int = 0
    total_files: int = 0
    total_size: int = 0
    structure_breakdown: Dict[StructureType, int] = field(default_factory=dict)
    folders: List[FolderAnalysis] = field(default_factory=list)
    conversion_feasibility: str = "high"  # high, medium, low
    estimated_conversion_time: str = "unknown"
    blocking_issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class BucketStructureScanner:
    """
    Scanner for analyzing bucket structures and determining conversion feasibility.
    Provides detailed analysis of folder types, OCFL compliance, and conversion requirements.
    """

    def __init__(self, bucket_service):
        """
        Initialize the scanner with bucket service.

        Args:
            bucket_service: BucketService instance for S3 operations
        """
        self.bucket_service = bucket_service

    def scan_bucket_structures(self, bucket_name: str) -> BucketAnalysis:
        """
        Scan entire bucket and categorize all folder structures.

        Args:
            bucket_name (str): Name of bucket to scan

        Returns:
            BucketAnalysis: Comprehensive analysis of bucket structure
        """
        logger.info(f"Starting bucket structure scan for {bucket_name}")

        analysis = BucketAnalysis(bucket_name=bucket_name)

        try:
            # Get all top-level collections in bucket
            collections = self._get_top_level_collections(bucket_name)
            analysis.total_folders = len(collections)

            logger.info(f"Found {len(collections)} top-level collections to analyze")

            # Initialize structure breakdown
            for structure_type in StructureType:
                analysis.structure_breakdown[structure_type] = 0

            # Analyze each collection
            for collection_path in collections:
                folder_analysis = self.analyze_folder_structure(bucket_name, collection_path)
                analysis.folders.append(folder_analysis)

                # Update counters
                analysis.total_files += folder_analysis.total_files
                analysis.total_size += folder_analysis.total_size
                analysis.structure_breakdown[folder_analysis.structure_type] += 1

                # Collect blocking issues
                analysis.blocking_issues.extend(folder_analysis.issues)

            # Generate overall recommendations
            self._generate_bucket_recommendations(analysis)

            logger.info(f"Completed bucket scan: {analysis.total_folders} collections, {analysis.total_files} files")

        except Exception as e:
            logger.error(f"Error scanning bucket {bucket_name}: {str(e)}")
            analysis.blocking_issues.append(f"Scan error: {str(e)}")
            analysis.conversion_feasibility = "low"

        return analysis

    def analyze_folder_structure(self, bucket_name: str, folder_path: str) -> FolderAnalysis:
        """
        Analyze individual folder structure and OCFL compliance.

        Args:
            bucket_name (str): Name of bucket containing folder
            folder_path (str): Path to folder to analyze

        Returns:
            FolderAnalysis: Detailed analysis of folder structure
        """
        logger.debug(f"Analyzing folder structure: {folder_path}")

        analysis = FolderAnalysis(folder_path=folder_path, structure_type=StructureType.UNKNOWN)

        try:
            # Get folder contents
            contents = self.bucket_service.list_bucket_contents(bucket_name, folder_path)

            if not contents:
                analysis.issues.append("Empty folder")
                return analysis

            # Analyze contents
            self._analyze_folder_contents(contents, analysis)

            # Determine structure type
            analysis.structure_type = self._determine_structure_type(analysis)

            # Set conversion complexity
            analysis.conversion_complexity = self._assess_conversion_complexity(analysis)

            # Generate recommendations
            self._generate_folder_recommendations(analysis)

        except Exception as e:
            logger.error(f"Error analyzing folder {folder_path}: {str(e)}")
            analysis.issues.append(f"Analysis error: {str(e)}")
            analysis.conversion_complexity = "high"

        return analysis

    def create_conversion_plan(self, bucket_analysis: BucketAnalysis) -> Dict[str, Any]:
        """
        Generate detailed conversion plan based on bucket analysis.

        Args:
            bucket_analysis: BucketAnalysis from scan_bucket_structures

        Returns:
            Dict containing conversion plan details
        """
        plan = {
            "bucket_name": bucket_analysis.bucket_name,
            "conversion_feasible": len(bucket_analysis.blocking_issues) == 0,
            "total_folders": bucket_analysis.total_folders,
            "conversion_phases": [],
            "estimated_duration": "unknown",
            "resource_requirements": {},
            "risk_assessment": "low",
            "rollback_strategy": {}
        }

        # Group folders by conversion complexity
        low_complexity = [f for f in bucket_analysis.folders if f.conversion_complexity == "low"]
        medium_complexity = [f for f in bucket_analysis.folders if f.conversion_complexity == "medium"]
        high_complexity = [f for f in bucket_analysis.folders if f.conversion_complexity == "high"]

        # Create phased approach
        if low_complexity:
            plan["conversion_phases"].append({
                "phase": 1,
                "name": "Low Complexity Conversions",
                "folders": [f.folder_path for f in low_complexity],
                "parallel_processing": True,
                "estimated_time": f"{len(low_complexity)} * 2 minutes"
            })

        if medium_complexity:
            plan["conversion_phases"].append({
                "phase": 2,
                "name": "Medium Complexity Conversions",
                "folders": [f.folder_path for f in medium_complexity],
                "parallel_processing": False,
                "estimated_time": f"{len(medium_complexity)} * 5 minutes"
            })

        if high_complexity:
            plan["conversion_phases"].append({
                "phase": 3,
                "name": "High Complexity Conversions",
                "folders": [f.folder_path for f in high_complexity],
                "parallel_processing": False,
                "estimated_time": f"{len(high_complexity)} * 15 minutes",
                "manual_review_required": True
            })

        # Set overall risk assessment
        if bucket_analysis.blocking_issues:
            plan["risk_assessment"] = "high"
        elif high_complexity or medium_complexity:
            plan["risk_assessment"] = "medium"

        return plan

    def validate_conversion_feasibility(self, bucket_analysis: BucketAnalysis) -> Dict[str, Any]:
        """
        Validate if bucket can be safely converted to OCFL.

        Args:
            bucket_analysis: BucketAnalysis from scan_bucket_structures

        Returns:
            Dict containing feasibility assessment
        """
        result = {
            "feasible": True,
            "confidence": "high",
            "blocking_issues": bucket_analysis.blocking_issues.copy(),
            "warnings": [],
            "requirements": [],
            "estimated_success_rate": 95
        }

        # Check for blocking issues
        if bucket_analysis.blocking_issues:
            result["feasible"] = False
            result["confidence"] = "low"
            result["estimated_success_rate"] = 20

        # Check structure distribution
        total_folders = bucket_analysis.total_folders
        if total_folders > 0:
            ocfl_folders = bucket_analysis.structure_breakdown.get(StructureType.FULL_OCFL, 0)
            unknown_folders = bucket_analysis.structure_breakdown.get(StructureType.UNKNOWN, 0)

            unknown_percentage = (unknown_folders / total_folders) * 100

            if unknown_percentage > 20:
                result["warnings"].append(f"{unknown_percentage:.1f}% of folders have unknown structure")
                result["confidence"] = "medium"
                result["estimated_success_rate"] -= 15

            if ocfl_folders / total_folders > 0.8:
                result["warnings"].append("Most folders already OCFL-compliant")

        # Add requirements
        high_complexity_folders = [f for f in bucket_analysis.folders if f.conversion_complexity == "high"]
        if high_complexity_folders:
            result["requirements"].append("Manual review required for high-complexity folders")
            result["estimated_success_rate"] -= 10

        return result

    def _get_top_level_collections(self, bucket_name: str) -> List[str]:
        """Get list of top-level collections in bucket"""
        try:
            contents = self.bucket_service.list_bucket_contents(bucket_name, "")
            collections = []

            for item in contents:
                if item.get("is_dir", False):
                    collections.append(item["name"])

            return collections
        except Exception as e:
            logger.error(f"Error getting top-level collections: {str(e)}")
            return []

    def _analyze_folder_contents(self, contents: List[Dict], analysis: FolderAnalysis) -> None:
        """Analyze folder contents and populate analysis flags"""
        for item in contents:
            name = item["name"]

            if name.startswith("0=ocfl_object_"):
                analysis.has_ocfl_marker = True

            if item.get("is_dir", False):
                # Check for OCFL directories
                if name == "v1":
                    analysis.has_version_directory = True
                elif name == "content":
                    analysis.has_content_directory = True
                elif name == "Resources":
                    analysis.has_resources_directory = True
            else:
                # Check for important files
                filename = name
                analysis.total_files += 1
                analysis.total_size += item.get("size", 0)

                if filename == "acl.json":
                    analysis.has_acl_file = True
                    analysis.preservation_requirements.append("ACL permissions")
                elif filename.endswith(".xml"):
                    analysis.xml_files.append(filename)
                    analysis.has_metadata_files = True
                    analysis.preservation_requirements.append("XML metadata")

    def _determine_structure_type(self, analysis: FolderAnalysis) -> StructureType:
        """Determine the structure type based on analysis flags"""
        if analysis.has_ocfl_marker and analysis.has_version_directory:
            if analysis.has_content_directory:
                return StructureType.FULL_OCFL
            else:
                return StructureType.PARTIAL_OCFL
        elif analysis.has_ocfl_marker or analysis.has_version_directory:
            return StructureType.PARTIAL_OCFL
        elif analysis.has_metadata_files and analysis.has_resources_directory:
            return StructureType.LEGACY_STRUCTURED
        elif analysis.has_metadata_files or analysis.has_resources_directory:
            return StructureType.LEGACY_FLAT
        elif analysis.total_files > 0:
            return StructureType.LEGACY_FLAT
        else:
            return StructureType.UNKNOWN

    def _assess_conversion_complexity(self, analysis: FolderAnalysis) -> str:
        """Assess conversion complexity based on structure analysis"""
        if analysis.structure_type == StructureType.FULL_OCFL:
            return "low"  # Already compliant
        elif analysis.structure_type == StructureType.PARTIAL_OCFL:
            return "medium"  # Needs completion
        elif analysis.structure_type == StructureType.LEGACY_STRUCTURED:
            return "low"  # Clear structure to convert
        elif analysis.structure_type == StructureType.LEGACY_FLAT:
            return "medium"  # Needs reorganization
        else:
            return "high"  # Unknown or mixed structure

    def _generate_folder_recommendations(self, analysis: FolderAnalysis) -> None:
        """Generate specific recommendations for folder conversion"""
        if analysis.structure_type == StructureType.FULL_OCFL:
            analysis.recommendations.append("Already OCFL-compliant, no conversion needed")
        elif analysis.structure_type == StructureType.PARTIAL_OCFL:
            analysis.recommendations.append("Complete existing OCFL structure")
            if not analysis.has_content_directory:
                analysis.recommendations.append("Add v1/content directory structure")
        elif analysis.structure_type == StructureType.LEGACY_STRUCTURED:
            analysis.recommendations.append("Convert to OCFL preserving existing structure")
            if analysis.has_acl_file:
                analysis.recommendations.append("Preserve ACL file in metadata directory")
        elif analysis.structure_type == StructureType.LEGACY_FLAT:
            analysis.recommendations.append("Reorganize files into OCFL structure")
        else:
            analysis.recommendations.append("Manual review required before conversion")
            analysis.issues.append("Unknown structure type requires investigation")

    def _generate_bucket_recommendations(self, analysis: BucketAnalysis) -> None:
        """Generate overall bucket conversion recommendations"""
        total = analysis.total_folders or len(analysis.folders)
        analysis.total_folders = total
        if total == 0:
            analysis.recommendations.append("Empty bucket, no conversion needed")
            return

        # Calculate percentages
        full_ocfl = analysis.structure_breakdown.get(StructureType.FULL_OCFL, 0)
        partial_ocfl = analysis.structure_breakdown.get(StructureType.PARTIAL_OCFL, 0)
        legacy = (analysis.structure_breakdown.get(StructureType.LEGACY_STRUCTURED, 0) +
                 analysis.structure_breakdown.get(StructureType.LEGACY_FLAT, 0))

        full_ocfl_pct = (full_ocfl / total) * 100
        legacy_pct = (legacy / total) * 100

        if analysis.blocking_issues:
            analysis.recommendations.append("Resolve blocking issues before conversion")
            analysis.conversion_feasibility = "low"
        elif full_ocfl_pct > 80:
            analysis.recommendations.append("Most folders already OCFL-compliant")
            analysis.conversion_feasibility = "high"
        elif legacy_pct > 60:
            analysis.recommendations.append("Good candidate for batch conversion")
            analysis.conversion_feasibility = "high"
        else:
            analysis.recommendations.append("Mixed structures, recommend phased conversion")
            analysis.conversion_feasibility = "medium"

        # Time estimation
        low_folders = sum(1 for f in analysis.folders if f.conversion_complexity == "low")
        medium_folders = sum(1 for f in analysis.folders if f.conversion_complexity == "medium")
        high_folders = sum(1 for f in analysis.folders if f.conversion_complexity == "high")

        estimated_minutes = (low_folders * 2) + (medium_folders * 5) + (high_folders * 15)
        if estimated_minutes < 60:
            analysis.estimated_conversion_time = f"{estimated_minutes} minutes"
        else:
            hours = estimated_minutes / 60
            analysis.estimated_conversion_time = f"{hours:.1f} hours"
