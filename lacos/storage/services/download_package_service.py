"""Build no-compression TAR packages for selected downloads."""

import json
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from pathlib import PurePosixPath
from typing import BinaryIO

from lacos.storage.services.download_script_service import DownloadScriptService
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.services.resource_resolver_service import ResolvedResource


@dataclass(frozen=True)
class TarPackageEntry:
    """A resolved object and its safe archive path."""

    archive_name: str
    bucket: str
    key: str
    filename: str
    size: int


class DownloadPackageTooLarge(Exception):
    """Raised when actual S3 object sizes exceed the package limit."""


class DownloadPackageService:
    """Create package-only TAR archives from S3 objects."""

    MANIFEST_NAME = "manifest.json"
    MAX_ERROR_FIELD_LENGTH = 128

    def __init__(self, s3_client=None):
        self.s3_client = s3_client or ResourceMappingService(skip_bucket_check=True).s3_client
        self.naming = DownloadScriptService()

    def archive_filename(self, entity_name: str) -> str:
        """Return a safe filename for the generated TAR package."""
        safe_name = self._safe_root_name(entity_name)
        return f"{safe_name}.tar"

    def create_tar_file(
        self,
        resources: list[ResolvedResource],
        entity_name: str,
        errors: list[dict] | None = None,
        max_total_size: int | None = None,
    ) -> BinaryIO:
        """Create a temporary TAR file containing the resolved resources."""
        root_name = self._safe_root_name(entity_name)
        entries = self._build_entries(resources, root_name)

        archive = tempfile.TemporaryFile()
        try:
            actual_total_size = 0
            manifest_files = []
            with tarfile.open(fileobj=archive, mode="w", format=tarfile.PAX_FORMAT) as tar:
                for entry in entries:
                    size = self._add_s3_object(
                        tar,
                        entry,
                        actual_total_size,
                        max_total_size,
                    )
                    actual_total_size += size
                    manifest_files.append({
                        "path": entry.archive_name,
                        "filename": entry.filename,
                        "size": size,
                    })
                self._add_manifest(
                    tar,
                    root_name,
                    manifest_files,
                    actual_total_size,
                    errors or [],
                )

            archive.seek(0)
            return archive
        except Exception:
            archive.close()
            raise

    def _build_entries(
        self,
        resources: list[ResolvedResource],
        root_name: str,
    ) -> list[TarPackageEntry]:
        existing: set[str] = {self.MANIFEST_NAME}
        entries: list[TarPackageEntry] = []

        for resource in resources:
            source_name = resource.filename or resource.key.split("/")[-1] or "download"
            filename = self.naming.sanitize_filename(source_name, existing)
            archive_name = f"{root_name}/{filename}"
            entries.append(
                TarPackageEntry(
                    archive_name=archive_name,
                    bucket=resource.bucket,
                    key=resource.key,
                    filename=filename,
                    size=resource.size or 0,
                )
            )

        return entries

    def _add_manifest(
        self,
        tar: tarfile.TarFile,
        root_name: str,
        files: list[dict],
        total_size: int,
        errors: list[dict],
    ) -> None:
        manifest = {
            "package_name": root_name,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "format": "tar",
            "compression": "none",
            "file_count": len(files),
            "total_size_bytes": total_size,
            "files": files,
            "skipped": self._safe_errors(errors),
        }
        body = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo(f"{root_name}/{self.MANIFEST_NAME}")
        info.size = len(body)
        info.mtime = 0
        info.mode = 0o644
        tar.addfile(info, fileobj=_BytesReader(body))

    def _add_s3_object(
        self,
        tar: tarfile.TarFile,
        entry: TarPackageEntry,
        current_total_size: int,
        max_total_size: int | None,
    ) -> int:
        response = self.s3_client.get_object(Bucket=entry.bucket, Key=entry.key)
        body = response["Body"]
        try:
            content_length = response.get("ContentLength")
            if content_length is None:
                raise ValueError("S3 object response missing ContentLength")
            size = int(content_length)
            if size < 0:
                raise ValueError("S3 object response has invalid ContentLength")
            if max_total_size is not None and current_total_size + size > max_total_size:
                raise DownloadPackageTooLarge("Package exceeds maximum size")
            self._validate_archive_name(entry.archive_name)
            info = tarfile.TarInfo(entry.archive_name)
            info.size = size
            info.mtime = 0
            info.mode = 0o644
            tar.addfile(info, fileobj=body)
            return size
        finally:
            close = getattr(body, "close", None)
            if close:
                close()

    def _safe_root_name(self, entity_name: str) -> str:
        safe_name = self.naming.sanitize_entity_name(entity_name or "download")
        safe_name = safe_name.strip().strip(". ")
        if not safe_name:
            safe_name = "download"
        safe_name = self.naming.sanitize_filename(safe_name, set()).strip().strip(". ")
        return safe_name or "download"

    def _safe_errors(self, errors: list[dict]) -> list[dict]:
        safe_errors = []
        for error in errors:
            safe_errors.append({
                "resource_id": self._safe_error_field(error.get("resource_id")),
                "error": self._safe_error_field(error.get("error")),
            })
        return safe_errors

    def _safe_error_field(self, value) -> str:
        text = str(value or "unknown")
        return text[:self.MAX_ERROR_FIELD_LENGTH]

    def _validate_archive_name(self, archive_name: str) -> None:
        path = PurePosixPath(archive_name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Unsafe archive path")


class _BytesReader:
    """Small read-only file object for tarfile.addfile."""

    def __init__(self, body: bytes):
        self._body = body
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._body) - self._offset
        start = self._offset
        end = min(len(self._body), start + size)
        self._offset = end
        return self._body[start:end]
