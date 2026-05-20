"""Service for generating download scripts (bash, PowerShell) and manifests."""

import re
import shlex
import unicodedata
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime


@dataclass
class DownloadInfo:
    """Information about a file to download."""

    filename: str  # Sanitized output filename
    url: str  # Presigned URL
    size: int  # File size in bytes
    checksum: str | None  # SHA-256 or None
    original_key: str  # Internal trace only; never included in user-facing output


# Windows reserved device names (case-insensitive)
WINDOWS_RESERVED_NAMES = frozenset([
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
])

# Characters invalid in Windows filenames
WINDOWS_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DownloadScriptService:
    """Generates download scripts and manifests for bundle downloads."""

    def sanitize_entity_name(self, name: str) -> str:
        """Sanitize an entity name for safe inclusion in generated scripts.

        Removes shell metacharacters that could be used for command injection.

        Args:
            name: Original entity name (bundle/collection name)

        Returns:
            Sanitized name with only safe characters
        """
        # Keep only alphanumeric, spaces, dashes, underscores, and periods
        safe_chars = []
        for char in name:
            if char.isalnum() or char in " -_.":
                safe_chars.append(char)
        sanitized = "".join(safe_chars)

        # Collapse multiple spaces and strip
        sanitized = " ".join(sanitized.split())

        # Ensure non-empty result
        return sanitized if sanitized else "unnamed"

    def sanitize_filename(self, filename: str, existing: set[str]) -> str:
        """Sanitize a filename for cross-platform compatibility.

        Args:
            filename: Original filename to sanitize
            existing: Set of already-used filenames (for duplicate handling)

        Returns:
            Sanitized filename that is unique within existing set
        """
        # Normalize Unicode to NFC
        filename = unicodedata.normalize("NFC", filename)

        # Replace Windows invalid characters with underscore
        filename = WINDOWS_INVALID_CHARS.sub("_", filename)

        # Handle empty or whitespace-only filenames
        filename = filename.strip()
        if not filename:
            filename = "unnamed"

        # Strip trailing dots and spaces (Windows limitation)
        filename = filename.rstrip(". ")
        if not filename:
            filename = "unnamed"

        # Check for Windows reserved names (case-insensitive, with or without extension)
        name_part = filename.rsplit(".", 1)[0] if "." in filename else filename
        if name_part.upper() in WINDOWS_RESERVED_NAMES:
            filename = "_" + filename

        # Handle duplicates
        if filename not in existing:
            existing.add(filename)
            return filename

        # Split name and extension for numbered duplicates
        if "." in filename:
            base, ext = filename.rsplit(".", 1)
            ext = "." + ext
        else:
            base = filename
            ext = ""

        counter = 1
        while True:
            candidate = f"{base}_{counter}{ext}"
            if candidate not in existing:
                existing.add(candidate)
                return candidate
            counter += 1

    def generate_bash_script(
        self,
        downloads: list[DownloadInfo],
        bundle_name: str,
        expires_at: datetime,
    ) -> str:
        """Generate a bash script for downloading files with curl.

        Args:
            downloads: List of files to download
            bundle_name: Name of the bundle
            expires_at: When the presigned URLs expire

        Returns:
            Complete bash script as a string
        """
        safe_bundle_name = self.sanitize_entity_name(bundle_name)
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        lines = [
            "#!/bin/bash",
            "set -euo pipefail",
            "",
            f"# Download script for bundle: {safe_bundle_name}",
            f"# Generated: {now_iso}",
            f"# WARNING: URLs expire at {expires_at.isoformat()}Z",
            "",
        ]

        if not downloads:
            lines.append("echo 'No files to download.'")
            lines.append("exit 0")
            return "\n".join(lines)

        lines.append(f"echo 'Downloading {len(downloads)} file(s)...'")
        lines.append("")

        # Download commands
        for i, dl in enumerate(downloads, 1):
            safe_filename = shlex.quote(dl.filename)
            safe_url = shlex.quote(dl.url)
            lines.append(
                f"echo '[{i}/{len(downloads)}] Downloading {safe_filename}...'",
            )
            lines.append(
                f"curl -L -C - --retry 3 --retry-connrefused -o {safe_filename} "
                f"{safe_url}",
            )
            lines.append("")

        # Checksum verification
        files_with_checksums = [dl for dl in downloads if dl.checksum]
        if files_with_checksums:
            lines.append("echo 'Verifying checksums...'")
            lines.append("sha256sum -c <<'CHECKSUMS'")
            for dl in files_with_checksums:
                safe_filename = dl.filename.replace("'", "'\\''")
                lines.append(f"{dl.checksum}  {safe_filename}")
            lines.append("CHECKSUMS")
            lines.append("")

        lines.append("echo 'Download complete!'")
        return "\n".join(lines)

    def generate_powershell_script(
        self,
        downloads: list[DownloadInfo],
        bundle_name: str,
        expires_at: datetime,
    ) -> str:
        """Generate a PowerShell script for downloading files.

        Args:
            downloads: List of files to download
            bundle_name: Name of the bundle
            expires_at: When the presigned URLs expire

        Returns:
            Complete PowerShell script as a string
        """
        safe_bundle_name = self.sanitize_entity_name(bundle_name)
        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        lines = [
            "# PowerShell download script",
            f"# Bundle: {safe_bundle_name}",
            f"# Generated: {now_iso}",
            f"# WARNING: URLs expire at {expires_at.isoformat()}Z",
            "",
            "$ErrorActionPreference = 'Stop'",
            "",
        ]

        if not downloads:
            lines.append("Write-Host 'No files to download.'")
            lines.append("exit 0")
            return "\n".join(lines)

        lines.append(f"Write-Host 'Downloading {len(downloads)} file(s)...'")
        lines.append("")

        # Download commands using Invoke-WebRequest
        for i, dl in enumerate(downloads, 1):
            safe_filename = self._escape_powershell_string(dl.filename)
            safe_url = self._escape_powershell_string(dl.url)
            lines.append(
                f"Write-Host '[{i}/{len(downloads)}] Downloading {safe_filename}...'",
            )
            lines.append(
                f"Invoke-WebRequest -Uri '{safe_url}' -OutFile '{safe_filename}'",
            )
            lines.append("")

        # Checksum verification
        files_with_checksums = [dl for dl in downloads if dl.checksum]
        if files_with_checksums:
            lines.append("Write-Host 'Verifying checksums...'")
            lines.append("$failed = $false")
            for dl in files_with_checksums:
                safe_filename = self._escape_powershell_string(dl.filename)
                lines.append(
                    "$hash = (Get-FileHash -Algorithm SHA256 "
                    f"'{safe_filename}').Hash.ToLower()",
                )
                lines.append(f"if ($hash -ne '{dl.checksum}') {{")
                lines.append(f"    Write-Host 'FAILED: {safe_filename}'")
                lines.append("    $failed = $true")
                lines.append("} else {")
                lines.append(f"    Write-Host 'OK: {safe_filename}'")
                lines.append("}")
            lines.append("if ($failed) { exit 1 }")
            lines.append("")

        lines.append("Write-Host 'Download complete!'")
        return "\n".join(lines)

    def _escape_powershell_string(self, value: str) -> str:
        """Escape a string for use in PowerShell single-quoted strings.

        In PowerShell single-quoted strings, the only special character is
        the single quote itself, which is escaped by doubling it.

        Args:
            value: String to escape

        Returns:
            Escaped string (without surrounding quotes)
        """
        return value.replace("'", "''")

    def generate_manifest(
        self,
        downloads: list[DownloadInfo],
        bundle_name: str,
        expires_at: datetime,
    ) -> dict:
        """Generate a JSON manifest for the download.

        Args:
            downloads: List of files to download
            bundle_name: Name of the bundle
            expires_at: When the presigned URLs expire

        Returns:
            Dictionary representing the manifest
        """
        return {
            "bundle_name": bundle_name,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat() + "Z",
            "file_count": len(downloads),
            "total_size_bytes": sum(dl.size for dl in downloads),
            "files": [
                {
                    "filename": dl.filename,
                    "url": dl.url,
                    "size": dl.size,
                    "checksum": dl.checksum,
                    "checksum_algorithm": "sha256" if dl.checksum else None,
                }
                for dl in downloads
            ],
        }
