"""Tests for no-compression TAR package generation."""

import io
import json
import tarfile

import pytest

from lacos.storage.services.download_package_service import DownloadPackageService, DownloadPackageTooLarge
from lacos.storage.services.resource_resolver_service import ResolvedResource


class FakeS3Client:
    def __init__(self, objects, include_content_length=True):
        self.objects = objects
        self.include_content_length = include_content_length

    def get_object(self, Bucket, Key):
        body = self.objects[(Bucket, Key)]
        response = {
            "Body": io.BytesIO(body),
        }
        if self.include_content_length:
            response["ContentLength"] = len(body)
        return response


@pytest.fixture
def resolved_resources():
    return [
        ResolvedResource(
            resource_id="res-1",
            bucket="test-bucket",
            key="audio/file.wav",
            filename="file.wav",
            size=11,
            checksum=None,
            presigned_url="https://example.test/file.wav",
        ),
        ResolvedResource(
            resource_id="res-2",
            bucket="test-bucket",
            key="metadata/file.wav",
            filename="file.wav",
            size=11,
            checksum=None,
            presigned_url="https://example.test/file-2.wav",
        ),
    ]


def test_create_tar_file_packages_selected_resources_without_compression(resolved_resources):
    s3 = FakeS3Client({
        ("test-bucket", "audio/file.wav"): b"audio-bytes",
        ("test-bucket", "metadata/file.wav"): b"meta-bytes!",
    })
    service = DownloadPackageService(s3_client=s3)

    archive = service.create_tar_file(resolved_resources, "Test Bundle")

    with tarfile.open(fileobj=archive, mode="r:") as tar:
        names = tar.getnames()
        assert names == [
            "Test Bundle/file.wav",
            "Test Bundle/file_1.wav",
            "Test Bundle/manifest.json",
        ]
        assert tar.extractfile("Test Bundle/file.wav").read() == b"audio-bytes"
        assert tar.extractfile("Test Bundle/file_1.wav").read() == b"meta-bytes!"

        manifest = json.loads(tar.extractfile("Test Bundle/manifest.json").read())
        assert manifest["compression"] == "none"
        assert manifest["file_count"] == 2
        assert manifest["total_size_bytes"] == 22
        assert manifest["files"][1]["filename"] == "file_1.wav"
        assert "original_key" not in manifest["files"][0]


def test_archive_filename_sanitizes_unsafe_entity_name():
    service = DownloadPackageService(s3_client=FakeS3Client({}))

    assert service.archive_filename("../") == "download.tar"
    assert service.archive_filename("CON") == "_CON.tar"


def test_create_tar_file_includes_skipped_resources_in_manifest(resolved_resources):
    s3 = FakeS3Client({
        ("test-bucket", "audio/file.wav"): b"audio-bytes",
        ("test-bucket", "metadata/file.wav"): b"meta-bytes!",
    })
    service = DownloadPackageService(s3_client=s3)
    errors = [{"resource_id": "res-3", "error": "access_denied", "message": "Denied"}]

    archive = service.create_tar_file(resolved_resources, "Test Bundle", errors=errors)

    with tarfile.open(fileobj=archive, mode="r:") as tar:
        manifest = json.loads(tar.extractfile("Test Bundle/manifest.json").read())
        assert manifest["skipped"] == [{"resource_id": "res-3", "error": "access_denied"}]


def test_create_tar_file_enforces_actual_s3_content_length(resolved_resources):
    s3 = FakeS3Client({
        ("test-bucket", "audio/file.wav"): b"audio-bytes",
        ("test-bucket", "metadata/file.wav"): b"meta-bytes!",
    })
    service = DownloadPackageService(s3_client=s3)

    with pytest.raises(DownloadPackageTooLarge):
        service.create_tar_file(
            resolved_resources,
            "Test Bundle",
            max_total_size=5,
        )


def test_create_tar_file_rejects_missing_s3_content_length(resolved_resources):
    s3 = FakeS3Client({
        ("test-bucket", "audio/file.wav"): b"audio-bytes",
        ("test-bucket", "metadata/file.wav"): b"meta-bytes!",
    }, include_content_length=False)
    service = DownloadPackageService(s3_client=s3)

    with pytest.raises(ValueError, match="ContentLength"):
        service.create_tar_file(resolved_resources, "Test Bundle")


def test_create_tar_file_sanitizes_archive_paths():
    resources = [
        ResolvedResource(
            resource_id="res-1",
            bucket="test-bucket",
            key="audio/../../evil.wav",
            filename="../../evil.wav",
            size=11,
            checksum=None,
            presigned_url="https://example.test/file.wav",
        ),
    ]
    s3 = FakeS3Client({
        ("test-bucket", "audio/../../evil.wav"): b"audio-bytes",
    })
    service = DownloadPackageService(s3_client=s3)

    archive = service.create_tar_file(resources, "../")

    with tarfile.open(fileobj=archive, mode="r:") as tar:
        names = tar.getnames()
        assert names == ["download/.._.._evil.wav", "download/manifest.json"]
        for name in names:
            assert not name.startswith("/")
            assert ".." not in name.split("/")
