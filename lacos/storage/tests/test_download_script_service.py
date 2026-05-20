"""Tests for the download script generation service."""

import json
from datetime import UTC
from datetime import datetime

import pytest

from lacos.storage.services.download_script_service import DownloadInfo
from lacos.storage.services.download_script_service import DownloadScriptService


@pytest.fixture
def service():
    """Create a DownloadScriptService instance."""
    return DownloadScriptService()


@pytest.fixture
def sample_downloads():
    """Create sample download info list for testing."""
    return [
        DownloadInfo(
            filename="file1.wav",
            url="https://example.com/file1?token=abc",
            size=1024,
            checksum="abc123def456",
            original_key="audio/file1.wav",
        ),
        DownloadInfo(
            filename="file2.txt",
            url="https://example.com/file2?token=xyz",
            size=512,
            checksum=None,
            original_key="docs/file2.txt",
        ),
    ]


@pytest.fixture
def expires_at():
    """Create a sample expiration datetime."""
    return datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)


# =============================================================================
# Tests for sanitize_filename
# =============================================================================


class TestSanitizeFilename:
    """Tests for the sanitize_filename method."""

    def test_simple_filename_unchanged(self, service):
        """Simple valid filename should remain unchanged."""
        existing = set()
        result = service.sanitize_filename("document.pdf", existing)
        assert result == "document.pdf"
        assert "document.pdf" in existing

    def test_duplicate_handling(self, service):
        """Duplicate filenames should get numbered suffixes."""
        existing = set()
        assert service.sanitize_filename("file.wav", existing) == "file.wav"
        assert service.sanitize_filename("file.wav", existing) == "file_1.wav"
        assert service.sanitize_filename("file.wav", existing) == "file_2.wav"

    def test_duplicate_no_extension(self, service):
        """Duplicate filenames without extension should be numbered."""
        existing = set()
        assert service.sanitize_filename("readme", existing) == "readme"
        assert service.sanitize_filename("readme", existing) == "readme_1"
        assert service.sanitize_filename("readme", existing) == "readme_2"

    def test_windows_reserved_names(self, service):
        """Windows reserved names should be prefixed with underscore."""
        existing = set()
        assert service.sanitize_filename("CON", existing) == "_CON"
        assert service.sanitize_filename("con", existing) == "_con"
        assert service.sanitize_filename("PRN.txt", existing) == "_PRN.txt"
        assert service.sanitize_filename("NUL.doc", existing) == "_NUL.doc"
        assert service.sanitize_filename("COM1", existing) == "_COM1"
        assert service.sanitize_filename("LPT9.log", existing) == "_LPT9.log"

    def test_windows_invalid_characters(self, service):
        """Invalid Windows characters should be replaced with underscore."""
        assert service.sanitize_filename("file<name>.txt", set()) == "file_name_.txt"
        assert service.sanitize_filename("file:name.txt", set()) == "file_name.txt"
        assert service.sanitize_filename('file"name.txt', set()) == "file_name.txt"
        assert service.sanitize_filename("file/name.txt", set()) == "file_name.txt"
        assert service.sanitize_filename("file\\name.txt", set()) == "file_name.txt"
        assert service.sanitize_filename("file|name.txt", set()) == "file_name.txt"
        assert service.sanitize_filename("file?name.txt", set()) == "file_name.txt"
        assert service.sanitize_filename("file*name.txt", set()) == "file_name.txt"

    def test_unicode_normalization(self, service):
        """Unicode should be normalized to NFC."""
        existing = set()
        # NFD form: u + combining diaeresis
        nfd_filename = "mu\u0308ller.txt"
        # NFC form: u-umlaut as single character
        nfc_expected = "m\u00fcller.txt"
        result = service.sanitize_filename(nfd_filename, existing)
        assert result == nfc_expected

    def test_unicode_filenames_preserved(self, service):
        """Valid Unicode characters should be preserved."""
        existing = set()
        assert service.sanitize_filename("日本語.txt", existing) == "日本語.txt"
        assert service.sanitize_filename("Ümläüt.wav", existing) == "Ümläüt.wav"
        assert service.sanitize_filename("中文文件.pdf", existing) == "中文文件.pdf"

    def test_empty_filename(self, service):
        """Empty filename should become 'unnamed'."""
        assert service.sanitize_filename("", set()) == "unnamed"
        assert service.sanitize_filename("   ", set()) == "unnamed"

    def test_only_invalid_chars(self, service):
        """Filename with only invalid chars should become 'unnamed'."""
        existing = set()
        # After replacing invalid chars and stripping, we get empty
        assert service.sanitize_filename("...", existing) == "unnamed"

    def test_trailing_dots_stripped(self, service):
        """Trailing dots should be stripped (Windows limitation)."""
        existing = set()
        assert service.sanitize_filename("file...", existing) == "file"
        assert service.sanitize_filename("test.txt.", existing) == "test.txt"

    def test_multiple_extensions(self, service):
        """Filenames with multiple dots should be handled correctly."""
        existing = set()
        assert service.sanitize_filename("archive.tar.gz", existing) == "archive.tar.gz"
        # Duplicate handling works on last extension
        result = service.sanitize_filename("archive.tar.gz", existing)
        assert result == "archive.tar_1.gz"


# =============================================================================
# Tests for generate_bash_script
# =============================================================================


class TestGenerateBashScript:
    """Tests for bash script generation."""

    def test_basic_script_structure(self, service, sample_downloads, expires_at):
        """Test basic bash script structure."""
        script = service.generate_bash_script(
            sample_downloads, "Test Bundle", expires_at,
        )

        assert script.startswith("#!/bin/bash")
        assert "set -euo pipefail" in script
        assert "Test Bundle" in script
        assert "2024-12-31T23:59:59" in script
        assert "Downloading 2 file(s)" in script
        assert "Download complete!" in script

    def test_curl_command_format(self, service, sample_downloads, expires_at):
        """Test curl command format with proper flags."""
        script = service.generate_bash_script(sample_downloads, "Bundle", expires_at)

        assert "curl -L -C - --retry 3 --retry-connrefused" in script

    def test_special_chars_bash_escaping_dollar(self, service, expires_at):
        """Test that dollar signs are properly escaped."""
        downloads = [
            DownloadInfo(
                filename="$variable.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        # shlex.quote should wrap in single quotes
        assert "'" in script
        assert "$variable.txt" in script

    def test_special_chars_bash_escaping_backtick(self, service, expires_at):
        """Test that backticks are properly escaped."""
        downloads = [
            DownloadInfo(
                filename="file`command`.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        # shlex.quote handles backticks
        assert "file`command`.txt" in script

    def test_special_chars_bash_escaping_single_quote(self, service, expires_at):
        """Test that single quotes in filenames are properly escaped."""
        downloads = [
            DownloadInfo(
                filename="file'quoted.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        # shlex.quote escapes single quotes specially
        assert "file" in script
        assert "quoted.txt" in script

    def test_special_chars_bash_escaping_double_quote(self, service, expires_at):
        """Test that double quotes are properly escaped."""
        downloads = [
            DownloadInfo(
                filename='file"double.txt',
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        assert 'file"double.txt' in script

    def test_special_chars_bash_escaping_spaces(self, service, expires_at):
        """Test that spaces are properly handled."""
        downloads = [
            DownloadInfo(
                filename="file with spaces.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        # shlex.quote wraps in quotes for spaces
        assert "'file with spaces.txt'" in script

    def test_special_chars_bash_escaping_newline(self, service, expires_at):
        """Test that newlines in filenames are properly escaped."""
        downloads = [
            DownloadInfo(
                filename="file\nname.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)
        # shlex.quote handles newlines with $'...' syntax
        assert "file" in script

    def test_checksum_verification(self, service, expires_at):
        """Test checksum verification is included when checksums present."""
        downloads = [
            DownloadInfo(
                filename="file1.txt",
                url="https://example.com/file1",
                size=100,
                checksum="abc123def456789",
                original_key="key1",
            ),
            DownloadInfo(
                filename="file2.txt",
                url="https://example.com/file2",
                size=200,
                checksum="xyz789abc123456",
                original_key="key2",
            ),
        ]
        script = service.generate_bash_script(downloads, "Bundle", expires_at)

        assert "sha256sum -c" in script
        assert "abc123def456789  file1.txt" in script
        assert "xyz789abc123456  file2.txt" in script
        assert "CHECKSUMS" in script

    def test_empty_downloads(self, service, expires_at):
        """Test script with no downloads."""
        script = service.generate_bash_script([], "Empty Bundle", expires_at)

        assert "#!/bin/bash" in script
        assert "No files to download" in script
        assert "exit 0" in script


# =============================================================================
# Tests for generate_powershell_script
# =============================================================================


class TestGeneratePowershellScript:
    """Tests for PowerShell script generation."""

    def test_basic_script_structure(self, service, sample_downloads, expires_at):
        """Test basic PowerShell script structure."""
        script = service.generate_powershell_script(
            sample_downloads, "Test Bundle", expires_at,
        )

        assert "# PowerShell download script" in script
        assert "Test Bundle" in script
        assert "2024-12-31T23:59:59" in script
        assert "$ErrorActionPreference = 'Stop'" in script
        assert "Downloading 2 file(s)" in script
        assert "Download complete!" in script

    def test_invoke_webrequest_format(self, service, sample_downloads, expires_at):
        """Test Invoke-WebRequest command format."""
        script = service.generate_powershell_script(
            sample_downloads, "Bundle", expires_at,
        )

        assert "Invoke-WebRequest -Uri" in script
        assert "-OutFile" in script

    def test_special_chars_powershell_single_quote(self, service, expires_at):
        """Test that single quotes are properly doubled."""
        downloads = [
            DownloadInfo(
                filename="file'quoted.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_powershell_script(downloads, "Bundle", expires_at)
        # Single quotes should be doubled in PowerShell
        assert "file''quoted.txt" in script

    def test_special_chars_powershell_double_quote(self, service, expires_at):
        """Test that double quotes don't need escaping in single-quoted strings."""
        downloads = [
            DownloadInfo(
                filename='file"double.txt',
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_powershell_script(downloads, "Bundle", expires_at)
        # Double quotes don't need escaping in single-quoted PowerShell strings
        assert 'file"double.txt' in script

    def test_special_chars_powershell_dollar(self, service, expires_at):
        """Test that dollar signs don't expand in single-quoted strings."""
        downloads = [
            DownloadInfo(
                filename="$variable.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_powershell_script(downloads, "Bundle", expires_at)
        # Dollar signs are literal in single-quoted PowerShell strings
        assert "$variable.txt" in script

    def test_special_chars_powershell_backtick(self, service, expires_at):
        """Test that backticks are handled in single-quoted strings."""
        downloads = [
            DownloadInfo(
                filename="file`name.txt",
                url="https://example.com/file",
                size=100,
                checksum=None,
                original_key="key",
            ),
        ]
        script = service.generate_powershell_script(downloads, "Bundle", expires_at)
        # Backticks are literal in single-quoted PowerShell strings
        assert "file`name.txt" in script

    def test_checksum_verification_powershell(self, service, expires_at):
        """Test checksum verification in PowerShell."""
        downloads = [
            DownloadInfo(
                filename="file1.txt",
                url="https://example.com/file1",
                size=100,
                checksum="abc123def456789",
                original_key="key1",
            ),
        ]
        script = service.generate_powershell_script(downloads, "Bundle", expires_at)

        assert "Get-FileHash -Algorithm SHA256" in script
        assert "abc123def456789" in script
        assert "$failed" in script

    def test_empty_downloads_powershell(self, service, expires_at):
        """Test PowerShell script with no downloads."""
        script = service.generate_powershell_script([], "Empty Bundle", expires_at)

        assert "# PowerShell download script" in script
        assert "No files to download" in script
        assert "exit 0" in script


# =============================================================================
# Tests for generate_manifest
# =============================================================================


class TestGenerateManifest:
    """Tests for JSON manifest generation."""

    def test_manifest_structure(self, service, sample_downloads, expires_at):
        """Test basic manifest structure."""
        manifest = service.generate_manifest(
            sample_downloads, "Test Bundle", expires_at,
        )

        assert manifest["bundle_name"] == "Test Bundle"
        assert "generated_at" in manifest
        assert manifest["expires_at"] == "2024-12-31T23:59:59+00:00Z"
        assert manifest["file_count"] == len(sample_downloads)
        expected_size = sample_downloads[0].size + sample_downloads[1].size
        assert manifest["total_size_bytes"] == expected_size
        assert len(manifest["files"]) == len(sample_downloads)

    def test_manifest_file_entry(self, service, sample_downloads, expires_at):
        """Test file entry structure in manifest."""
        manifest = service.generate_manifest(sample_downloads, "Bundle", expires_at)

        file1 = manifest["files"][0]
        assert file1["filename"] == "file1.wav"
        assert file1["url"] == "https://example.com/file1?token=abc"
        assert file1["size"] == sample_downloads[0].size
        assert file1["checksum"] == "abc123def456"
        assert file1["checksum_algorithm"] == "sha256"
        assert "original_key" not in file1

        file2 = manifest["files"][1]
        assert file2["checksum"] is None
        assert file2["checksum_algorithm"] is None

    def test_manifest_json_serializable(self, service, sample_downloads, expires_at):
        """Test that manifest is JSON serializable."""
        manifest = service.generate_manifest(sample_downloads, "Bundle", expires_at)

        # Should not raise
        json_str = json.dumps(manifest)
        parsed = json.loads(json_str)
        assert parsed["bundle_name"] == "Bundle"

    def test_empty_downloads_manifest(self, service, expires_at):
        """Test manifest with no downloads."""
        manifest = service.generate_manifest([], "Empty Bundle", expires_at)

        assert manifest["bundle_name"] == "Empty Bundle"
        assert manifest["file_count"] == 0
        assert manifest["total_size_bytes"] == 0
        assert manifest["files"] == []

    def test_manifest_unicode_filenames(self, service, expires_at):
        """Test manifest with Unicode filenames."""
        downloads = [
            DownloadInfo(
                filename="日本語ファイル.txt",
                url="https://example.com/file",
                size=100,
                checksum="abc123",
                original_key="key",
            ),
        ]
        manifest = service.generate_manifest(downloads, "Unicode Bundle", expires_at)

        assert manifest["files"][0]["filename"] == "日本語ファイル.txt"
        # Should be JSON serializable
        json_str = json.dumps(manifest, ensure_ascii=False)
        assert "日本語ファイル.txt" in json_str
