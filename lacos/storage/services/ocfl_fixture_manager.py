import logging
import json
import os
import tempfile
import shutil
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import datetime

logger = logging.getLogger(__name__)


@dataclass
class PreservationMetadata:
    """Metadata extracted for preservation during OCFL conversion"""
    acl_data: Optional[Dict] = None
    xml_files: Dict[str, str] = field(default_factory=dict)  # filename -> content
    ocfl_markers: List[str] = field(default_factory=list)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)
    directory_structure: Dict[str, Any] = field(default_factory=dict)
    file_permissions: Dict[str, str] = field(default_factory=dict)
    extraction_timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())


@dataclass
class FixtureBackup:
    """Backup information for rollback capability"""
    backup_id: str
    original_path: str
    backup_location: str
    metadata: PreservationMetadata
    creation_timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())


class OCFLFixtureManager:
    """
    Manager for extracting, preserving, and applying metadata during OCFL conversions.
    Handles ACLs, XML files, existing OCFL markers, and custom metadata preservation.
    """

    def __init__(self, bucket_service, temp_storage_path: Optional[str] = None):
        """
        Initialize the fixture manager.

        Args:
            bucket_service: BucketService instance for S3 operations
            temp_storage_path: Optional path for temporary storage, uses system temp if None
        """
        self.bucket_service = bucket_service
        self.temp_storage_path = temp_storage_path or tempfile.gettempdir()
        self.active_backups: Dict[str, FixtureBackup] = {}

    def extract_existing_metadata(self, bucket_name: str, folder_path: str) -> PreservationMetadata:
        """
        Extract all existing metadata from folder for preservation.

        Args:
            bucket_name (str): Name of bucket containing folder
            folder_path (str): Path to folder to extract metadata from

        Returns:
            PreservationMetadata: All extracted metadata
        """
        logger.info("Extracting metadata", extra={"folder_path": folder_path})

        metadata = PreservationMetadata()

        try:
            # Get folder contents
            contents = self.bucket_service.list_bucket_contents(bucket_name, folder_path)

            if not contents:
                logger.warning("No contents found", extra={"folder_path": folder_path})
                return metadata

            # Extract different types of metadata
            self._extract_acl_data(bucket_name, folder_path, contents, metadata)
            self._extract_xml_files(bucket_name, folder_path, contents, metadata)
            self._extract_ocfl_markers(contents, metadata)
            self._extract_directory_structure(contents, metadata)
            self._extract_custom_metadata(bucket_name, folder_path, contents, metadata)

            logger.info("Successfully extracted metadata", extra={
                "xml_files_count": len(metadata.xml_files),
                "has_acl_data": metadata.acl_data is not None,
                "ocfl_markers_count": len(metadata.ocfl_markers),
            })

        except Exception as e:
            logger.error("Error extracting metadata", extra={"folder_path": folder_path, "error": str(e)})
            metadata.custom_metadata["extraction_error"] = str(e)

        return metadata

    def apply_fixtures(self, bucket_name: str, ocfl_folder_path: str,
                      metadata: PreservationMetadata) -> Dict[str, Any]:
        """
        Apply preserved metadata to new OCFL structure.

        Args:
            bucket_name (str): Name of target bucket
            ocfl_folder_path (str): Path to OCFL structure
            metadata (PreservationMetadata): Metadata to apply

        Returns:
            Dict containing application results
        """
        logger.info("Applying fixtures to OCFL structure", extra={"ocfl_folder_path": ocfl_folder_path})

        results = {
            "success": True,
            "applied_fixtures": [],
            "skipped_fixtures": [],
            "errors": []
        }

        try:
            # Create metadata directory if it doesn't exist
            metadata_path = f"{ocfl_folder_path.rstrip('/')}/v1/content/metadata"
            self._ensure_directory_exists(bucket_name, metadata_path)

            # Apply ACL data
            if metadata.acl_data:
                self._apply_acl_data(bucket_name, metadata_path, metadata.acl_data, results)

            # Apply XML files
            self._apply_xml_files(bucket_name, metadata_path, metadata.xml_files, results)

            # Apply OCFL markers (if converting partial OCFL)
            self._apply_ocfl_markers(bucket_name, ocfl_folder_path, metadata.ocfl_markers, results)

            # Apply custom metadata
            self._apply_custom_metadata(bucket_name, metadata_path, metadata.custom_metadata, results)

            logger.info("Applied fixtures successfully", extra={"count": len(results['applied_fixtures'])})

        except Exception as e:
            logger.error("Error applying fixtures", extra={"error": str(e)})
            results["success"] = False
            results["errors"].append(str(e))

        if results["errors"]:
            results["success"] = False

        return results

    def create_fixture_backup(self, bucket_name: str, folder_path: str) -> str:
        """
        Create backup of existing metadata for rollback.

        Args:
            bucket_name (str): Name of bucket
            folder_path (str): Path to folder to backup

        Returns:
            str: Backup ID for later reference
        """
        logger.info("Creating fixture backup", extra={"folder_path": folder_path})

        backup_id = f"backup_{folder_path.replace('/', '_')}_{int(datetime.datetime.now().timestamp())}"

        try:
            # Extract current metadata
            metadata = self.extract_existing_metadata(bucket_name, folder_path)

            # Create backup location
            backup_location = os.path.join(self.temp_storage_path, "ocfl_backups", backup_id)
            os.makedirs(backup_location, exist_ok=True)

            # Download original folder structure
            self._download_folder_for_backup(bucket_name, folder_path, backup_location)

            # Create backup record
            backup = FixtureBackup(
                backup_id=backup_id,
                original_path=folder_path,
                backup_location=backup_location,
                metadata=metadata
            )

            # Save backup metadata
            backup_metadata_file = os.path.join(backup_location, "backup_metadata.json")
            with open(backup_metadata_file, 'w') as f:
                # Convert backup to dict for JSON serialization
                backup_dict = {
                    "backup_id": backup.backup_id,
                    "original_path": backup.original_path,
                    "backup_location": backup.backup_location,
                    "creation_timestamp": backup.creation_timestamp,
                    "metadata": {
                        "acl_data": metadata.acl_data,
                        "xml_files": metadata.xml_files,
                        "ocfl_markers": metadata.ocfl_markers,
                        "custom_metadata": metadata.custom_metadata,
                        "directory_structure": metadata.directory_structure,
                        "extraction_timestamp": metadata.extraction_timestamp
                    }
                }
                json.dump(backup_dict, f, indent=2)

            # Store active backup
            self.active_backups[backup_id] = backup

            logger.info("Created backup", extra={"backup_id": backup_id, "backup_location": backup_location})
            return backup_id

        except Exception as e:
            logger.error("Error creating backup", extra={"folder_path": folder_path, "error": str(e)})
            raise

    def restore_from_backup(self, backup_id: str, target_bucket: str) -> Dict[str, Any]:
        """
        Restore folder from backup.

        Args:
            backup_id (str): ID of backup to restore
            target_bucket (str): Bucket to restore to

        Returns:
            Dict containing restoration results
        """
        logger.info("Restoring from backup", extra={"backup_id": backup_id})

        if backup_id not in self.active_backups:
            # Try to load backup from file
            self._load_backup_from_file(backup_id)

        if backup_id not in self.active_backups:
            return {
                "success": False,
                "error": f"Backup {backup_id} not found"
            }

        backup = self.active_backups[backup_id]

        try:
            # Upload backup contents to target location
            result = self.bucket_service._upload_directory(
                backup.backup_location,
                target_bucket,
                backup.original_path
            )

            if result["success"]:
                logger.info("Successfully restored from backup", extra={"original_path": backup.original_path, "backup_id": backup_id})
                return {
                    "success": True,
                    "message": f"Restored {backup.original_path}",
                    "files_restored": result.get("total_files", 0)
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to upload backup: {result.get('error', 'Unknown error')}"
                }

        except Exception as e:
            logger.error("Error restoring backup", extra={"backup_id": backup_id, "error": str(e)})
            return {
                "success": False,
                "error": str(e)
            }

    def cleanup_backup(self, backup_id: str) -> bool:
        """
        Clean up backup files and remove from active backups.

        Args:
            backup_id (str): ID of backup to clean up

        Returns:
            bool: True if cleanup successful
        """
        try:
            if backup_id in self.active_backups:
                backup = self.active_backups[backup_id]

                # Remove backup files
                if os.path.exists(backup.backup_location):
                    shutil.rmtree(backup.backup_location)

                # Remove from active backups
                del self.active_backups[backup_id]

                logger.info("Cleaned up backup", extra={"backup_id": backup_id})
                return True
            else:
                logger.warning("Backup not found in active backups", extra={"backup_id": backup_id})
                return False

        except Exception as e:
            logger.error("Error cleaning up backup", extra={"backup_id": backup_id, "error": str(e)})
            return False

    def list_active_backups(self) -> List[Dict[str, Any]]:
        """
        List all active backups.

        Returns:
            List of backup information
        """
        backups = []
        for backup_id, backup in self.active_backups.items():
            backups.append({
                "backup_id": backup_id,
                "original_path": backup.original_path,
                "creation_timestamp": backup.creation_timestamp,
                "has_acl": backup.metadata.acl_data is not None,
                "xml_files_count": len(backup.metadata.xml_files),
                "ocfl_markers_count": len(backup.metadata.ocfl_markers)
            })
        return backups

    def _extract_acl_data(self, bucket_name: str, folder_path: str,
                          contents: List[Dict], metadata: PreservationMetadata) -> None:
        """Extract ACL data from folder"""
        for item in contents:
            if not item.get("is_dir", False) and item["name"] == "acl.json":
                try:
                    # Download ACL file content
                    acl_key = f"{folder_path.rstrip('/')}/{item['name']}"
                    response = self.bucket_service.s3_client.get_object(
                        Bucket=bucket_name, Key=acl_key
                    )
                    body = None
                    if isinstance(response, dict):
                        body = response.get("Body")
                    else:
                        body = getattr(response, "Body", None)
                    if body is None and hasattr(response, "_mock_children"):
                        body = response._mock_children.get("Body")
                        if body is None:
                            try:
                                body = response["Body"]  # type: ignore[index]
                            except (TypeError, KeyError, AttributeError):
                                body = None
                    if body is None:
                        raise KeyError("Body")

                    acl_content = body.read().decode('utf-8')
                    metadata.acl_data = json.loads(acl_content)
                    logger.debug("Extracted ACL data", extra={"acl_key": acl_key})
                except Exception as e:
                    logger.warning("Failed to extract ACL data", extra={"error": str(e)})
                    metadata.custom_metadata.setdefault("extraction_error", str(e))

    def _extract_xml_files(self, bucket_name: str, folder_path: str,
                          contents: List[Dict], metadata: PreservationMetadata) -> None:
        """Extract XML files from folder"""
        for item in contents:
            if not item.get("is_dir", False) and item["name"].endswith(".xml"):
                try:
                    xml_key = f"{folder_path.rstrip('/')}/{item['name']}"
                    response = self.bucket_service.s3_client.get_object(
                        Bucket=bucket_name, Key=xml_key
                    )
                    body = None
                    if isinstance(response, dict):
                        body = response.get("Body")
                    else:
                        body = getattr(response, "Body", None)
                    if body is None and hasattr(response, "_mock_children"):
                        body = response._mock_children.get("Body")
                        if body is None:
                            try:
                                body = response["Body"]  # type: ignore[index]
                            except (TypeError, KeyError, AttributeError):
                                body = None
                    if body is None:
                        raise KeyError("Body")

                    xml_content = body.read().decode('utf-8')
                    metadata.xml_files[item["name"]] = xml_content
                    logger.debug("Extracted XML file", extra={"file_name": item['name']})
                except Exception as e:
                    logger.warning("Failed to extract XML file", extra={"file_name": item['name'], "error": str(e)})
                    metadata.custom_metadata.setdefault("extraction_error", str(e))

    def _extract_ocfl_markers(self, contents: List[Dict], metadata: PreservationMetadata) -> None:
        """Extract OCFL version markers"""
        for item in contents:
            if item["name"].startswith("0=ocfl_object_"):
                metadata.ocfl_markers.append(item["name"])
                logger.debug("Found OCFL marker", extra={"marker": item['name']})

    def _extract_directory_structure(self, contents: List[Dict], metadata: PreservationMetadata) -> None:
        """Extract directory structure for preservation"""
        directories = []
        files = []

        for item in contents:
            if item.get("is_dir", False):
                directories.append(item["name"])
            else:
                files.append({
                    "name": item["name"],
                    "size": item.get("size", 0),
                    "last_modified": item.get("last_modified", "unknown")
                })

        metadata.directory_structure = {
            "directories": directories,
            "files": files,
            "total_items": len(contents)
        }

    def _extract_custom_metadata(self, bucket_name: str, folder_path: str,
                                contents: List[Dict], metadata: PreservationMetadata) -> None:
        """Extract any custom metadata files"""
        custom_files = [".metadata", "manifest.json", "description.txt", "readme.txt"]

        for item in contents:
            if not item.get("is_dir", False) and item["name"].lower() in custom_files:
                try:
                    custom_key = f"{folder_path.rstrip('/')}/{item['name']}"
                    response = self.bucket_service.s3_client.get_object(
                        Bucket=bucket_name, Key=custom_key
                    )
                    content = response['Body'].read().decode('utf-8')
                    metadata.custom_metadata[item["name"]] = content
                    logger.debug("Extracted custom metadata file", extra={"file_name": item['name']})
                except Exception as e:
                    logger.warning("Failed to extract custom metadata", extra={"file_name": item['name'], "error": str(e)})

    def _ensure_directory_exists(self, bucket_name: str, directory_path: str) -> None:
        """Ensure directory exists in S3 by creating a directory marker"""
        try:
            directory_key = f"{directory_path.rstrip('/')}/"
            self.bucket_service.s3_client.put_object(
                Bucket=bucket_name,
                Key=directory_key,
                Body=""
            )
        except Exception as e:
            logger.warning("Failed to create directory marker", extra={"directory_path": directory_path, "error": str(e)})

    def _apply_acl_data(self, bucket_name: str, metadata_path: str,
                       acl_data: Dict, results: Dict) -> None:
        """Apply ACL data to metadata directory"""
        try:
            acl_key = f"{metadata_path.rstrip('/')}/acl.json"
            self.bucket_service.s3_client.put_object(
                Bucket=bucket_name,
                Key=acl_key,
                Body=json.dumps(acl_data, indent=2)
            )
            results["applied_fixtures"].append("acl.json")
            logger.debug("Applied ACL data", extra={"acl_key": acl_key})
        except Exception as e:
            results["errors"].append(f"Failed to apply ACL data: {str(e)}")

    def _apply_xml_files(self, bucket_name: str, metadata_path: str,
                        xml_files: Dict[str, str], results: Dict) -> None:
        """Apply XML files to metadata directory"""
        for filename, content in xml_files.items():
            try:
                xml_key = f"{metadata_path.rstrip('/')}/{filename}"
                self.bucket_service.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=xml_key,
                    Body=content
                )
                results["applied_fixtures"].append(filename)
                logger.debug("Applied XML file", extra={"file_name": filename})
            except Exception as e:
                results["errors"].append(f"Failed to apply XML file {filename}: {str(e)}")

    def _apply_ocfl_markers(self, bucket_name: str, ocfl_folder_path: str,
                          ocfl_markers: List[str], results: Dict) -> None:
        """Apply OCFL markers to folder"""
        for marker in ocfl_markers:
            try:
                marker_key = f"{ocfl_folder_path.rstrip('/')}/{marker}"
                self.bucket_service.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=marker_key,
                    Body=""
                )
                results["applied_fixtures"].append(marker)
                logger.debug("Applied OCFL marker", extra={"marker": marker})
            except Exception as e:
                results["errors"].append(f"Failed to apply OCFL marker {marker}: {str(e)}")

    def _apply_custom_metadata(self, bucket_name: str, metadata_path: str,
                             custom_metadata: Dict[str, Any], results: Dict) -> None:
        """Apply custom metadata files"""
        for filename, content in custom_metadata.items():
            if filename == "extraction_error":
                continue  # Skip error messages

            try:
                custom_key = f"{metadata_path.rstrip('/')}/{filename}"
                content_str = content if isinstance(content, str) else json.dumps(content, indent=2)
                self.bucket_service.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=custom_key,
                    Body=content_str
                )
                results["applied_fixtures"].append(filename)
                logger.debug("Applied custom metadata", extra={"file_name": filename})
            except Exception as e:
                results["errors"].append(f"Failed to apply custom metadata {filename}: {str(e)}")

    def _download_folder_for_backup(self, bucket_name: str, folder_path: str,
                                   backup_location: str) -> None:
        """Download folder contents for backup"""
        try:
            self.bucket_service._download_directory(bucket_name, folder_path, backup_location)
        except Exception as e:
            logger.error("Failed to download folder for backup", extra={"error": str(e)})
            raise

    def _load_backup_from_file(self, backup_id: str) -> None:
        """Load backup information from file"""
        try:
            backup_metadata_file = os.path.join(
                self.temp_storage_path, "ocfl_backups", backup_id, "backup_metadata.json"
            )

            if os.path.exists(backup_metadata_file):
                with open(backup_metadata_file, 'r') as f:
                    backup_data = json.load(f)

                # Reconstruct backup object
                metadata = PreservationMetadata(
                    acl_data=backup_data["metadata"]["acl_data"],
                    xml_files=backup_data["metadata"]["xml_files"],
                    ocfl_markers=backup_data["metadata"]["ocfl_markers"],
                    custom_metadata=backup_data["metadata"]["custom_metadata"],
                    directory_structure=backup_data["metadata"]["directory_structure"],
                    extraction_timestamp=backup_data["metadata"]["extraction_timestamp"]
                )

                backup = FixtureBackup(
                    backup_id=backup_data["backup_id"],
                    original_path=backup_data["original_path"],
                    backup_location=backup_data["backup_location"],
                    metadata=metadata,
                    creation_timestamp=backup_data["creation_timestamp"]
                )

                self.active_backups[backup_id] = backup
                logger.debug("Loaded backup from file", extra={"backup_id": backup_id})

        except Exception as e:
            logger.warning("Failed to load backup from file", extra={"backup_id": backup_id, "error": str(e)})
