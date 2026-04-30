from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from botocore.exceptions import ClientError

from lacos.blam.models.bundle.bundle_structural_info import BundleAdditionalMetadataFile
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.explorer.views.utils.storage import load_xml_preview, resolve_resource_to_presigned
from lacos.explorer.views.utils.storage import resolve_collection_metadata_to_presigned
from lacos.explorer.views.utils.storage import load_markdown_preview


def _not_found_error():
    return ClientError(
        {
            "Error": {
                "Code": "NoSuchKey",
                "Message": "The specified key does not exist.",
            },
        },
        "HeadObject",
    )


def test_resolve_resource_to_presigned_syncs_resolved_location(monkeypatch):
    """Resolved fallback bucket/key should be synced to S3ResourceLocation."""
    resource = SimpleNamespace(
        id="resource-1",
        file_name="burung_KOW.imdi",
        file_pid="hdl:11341/0000-0000-0000-3D03",
    )
    bundle = SimpleNamespace(
        id="bundle-1",
        import_bucket=None,
        import_object_key=None,
    )

    service = MagicMock()
    service.production_bucket = "grails-dev"
    service.resolve_pid_to_s3.return_value = None
    service.generate_presigned_url.return_value = "https://example.test/presigned"

    monkeypatch.setattr(
        "lacos.explorer.views.utils.storage.resolve_existing_object",
        lambda _service, _candidates: (
            "grails-dev",
            "wooi_archive_cologne/burung_kow/v1/content/Resources/burung_KOW.imdi",
        ),
    )

    result = resolve_resource_to_presigned(
        service,
        resource,
        bundle,
        collection_for_path=None,
    )

    assert result is not None
    assert result["bucket"] == "grails-dev"
    assert result["key"].endswith("burung_KOW.imdi")
    assert result["url"] == "https://example.test/presigned"
    service.register_s3_location.assert_called_once_with(
        resource,
        "grails-dev",
        "wooi_archive_cologne/burung_kow/v1/content/Resources/burung_KOW.imdi",
        pid_url="hdl:11341/0000-0000-0000-3D03",
        fetch_metadata=False,
    )


def test_resolve_resource_to_presigned_uses_existing_location_when_object_exists(
    monkeypatch,
):
    resource = SimpleNamespace(
        id="resource-1",
        file_name="clip.wav",
        file_pid="hdl:11341/0000-0000-0000-AAAA",
    )
    bundle = SimpleNamespace(id="bundle-1", import_bucket=None, import_object_key=None)

    service = MagicMock()
    service.resolve_pid_to_s3.return_value = SimpleNamespace(
        s3_bucket="grails-dev",
        s3_key="already/mapped/clip.wav",
    )
    service.generate_presigned_url.return_value = "https://example.test/existing"

    result = resolve_resource_to_presigned(
        service,
        resource,
        bundle,
        collection_for_path=None,
    )

    assert result == {
        "bucket": "grails-dev",
        "key": "already/mapped/clip.wav",
        "url": "https://example.test/existing",
    }
    service.generate_presigned_url.assert_called_once_with(
        "grails-dev",
        "already/mapped/clip.wav",
        response_headers=None,
    )
    service.s3_client.head_object.assert_called_once_with(
        Bucket="grails-dev",
        Key="already/mapped/clip.wav",
    )


def test_resolve_resource_to_presigned_ignores_stale_mapped_location(monkeypatch):
    resource_key = (
        "ivac_explorations/chankaquechua_1/v1/content/"
        "chankaquechua-0001-part2.mp4"
    )
    resource = SimpleNamespace(
        id="resource-1",
        file_name="chankaquechua-0001-part2.mp4",
        file_pid="hdl:11341/0000-0000-0000-43E0",
    )
    bundle = SimpleNamespace(
        id="chankaquechua_1",
        import_bucket="lacos-ingest",
        import_object_key=(
            "ivac_explorations/chankaquechua_1/v1/metadata/"
            "chankaquechua_1.xml"
        ),
    )
    collection = SimpleNamespace(
        id="ivac_explorations",
        import_bucket=None,
        import_object_key=None,
    )

    service = MagicMock()
    service.production_bucket = "lacos-production"
    service.resolve_pid_to_s3.return_value = SimpleNamespace(
        s3_bucket="lacos-ingest",
        s3_key=resource_key,
    )
    service.generate_presigned_url.return_value = "https://example.test/production"

    def head_object(**kwargs):
        bucket = kwargs["Bucket"]
        key = kwargs["Key"]
        if bucket == "lacos-ingest":
            raise _not_found_error()
        assert bucket == "lacos-production"
        assert key == resource_key
        return {}

    service.s3_client.head_object.side_effect = head_object

    result = resolve_resource_to_presigned(service, resource, bundle, collection)

    assert result == {
        "bucket": "lacos-production",
        "key": resource_key,
        "url": "https://example.test/production",
    }
    service.generate_presigned_url.assert_called_once_with(
        "lacos-production",
        resource_key,
        response_headers=None,
    )
    service.register_s3_location.assert_called_once_with(
        resource,
        "lacos-production",
        resource_key,
        pid_url="hdl:11341/0000-0000-0000-43E0",
        fetch_metadata=False,
    )
    assert service.s3_client.head_object.call_args_list[:2] == [
        call(
            Bucket="lacos-ingest",
            Key=resource_key,
        ),
        call(
            Bucket="lacos-production",
            Key=resource_key,
        ),
    ]


@pytest.mark.django_db
def test_resolve_resource_to_presigned_bundle_metadata_uses_additional_metadata_path(monkeypatch):
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_name="bundle-metadata.xml",
        file_pid="hdl:11341/0000-0000-0000-BBBB",
        mime_type="application/xml",
        is_metadata_for="bundle",
    )
    bundle = SimpleNamespace(
        id="bundle-1",
        import_bucket="grails-dev",
        import_object_key="test-coll/bundle-1/v1/metadata/bundle-1.xml",
    )

    seen_candidates = []
    service = MagicMock()
    service.production_bucket = "lacos-production"
    service.resolve_pid_to_s3.return_value = None
    service.generate_presigned_url.return_value = "https://example.test/bundle-metadata"
    service._get_ocfl_additional_metadata_base_path.return_value = (
        "test-coll/bundle-1/v1/metadata/additional_metadata/"
    )

    def capture_candidates(_service, candidates):
        seen_candidates.extend(candidates)
        return candidates[0]

    monkeypatch.setattr(
        "lacos.explorer.views.utils.storage.resolve_existing_object",
        capture_candidates,
    )

    result = resolve_resource_to_presigned(service, metadata_file, bundle, collection_for_path=None)

    assert result["key"] == "test-coll/bundle-1/v1/metadata/additional_metadata/bundle-metadata.xml"
    assert seen_candidates == [
        ("grails-dev", "test-coll/bundle-1/v1/metadata/additional_metadata/bundle-metadata.xml"),
    ]


@pytest.mark.django_db
def test_resolve_collection_metadata_to_presigned_falls_back_to_ocfl_additional_metadata_path(monkeypatch):
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_name="collection-metadata.imdi",
        file_pid="hdl:11341/0000-0000-0000-CCCC",
        mime_type="application/xml",
        is_metadata_for="collection",
    )
    collection = SimpleNamespace(
        import_bucket="grails-dev",
        import_object_key="test-coll/v1/metadata/test-coll.xml",
    )

    seen_candidates = []
    service = MagicMock()
    service.production_bucket = "lacos-production"
    service.resolve_pid_to_s3.return_value = None
    service.generate_presigned_url.return_value = "https://example.test/collection-metadata"
    service._get_ocfl_additional_metadata_base_path.return_value = (
        "test-coll/v1/metadata/additional_metadata/"
    )

    def capture_candidates(_service, candidates):
        seen_candidates.extend(candidates)
        return candidates[0]

    monkeypatch.setattr(
        "lacos.explorer.views.utils.storage.resolve_existing_object",
        capture_candidates,
    )

    result = resolve_collection_metadata_to_presigned(service, metadata_file, collection)

    assert result["key"] == "test-coll/v1/metadata/additional_metadata/collection-metadata.imdi"
    assert seen_candidates[0] == (
        "grails-dev",
        "test-coll/v1/metadata/additional_metadata/collection-metadata.imdi",
    )
    service.register_s3_location.assert_called_once_with(
        metadata_file,
        "grails-dev",
        "test-coll/v1/metadata/additional_metadata/collection-metadata.imdi",
        pid_url="hdl:11341/0000-0000-0000-CCCC",
        fetch_metadata=False,
    )


@pytest.mark.django_db
def test_resolve_collection_metadata_to_presigned_ignores_stale_mapped_location(
    monkeypatch,
):
    metadata_key = (
        "ivac_explorations/v1/metadata/additional_metadata/"
        "collection-metadata.imdi"
    )
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_name="collection-metadata.imdi",
        file_pid="hdl:11341/0000-0000-0000-DDDD",
        mime_type="application/xml",
        is_metadata_for="collection",
    )
    collection = SimpleNamespace(
        import_bucket="lacos-ingest",
        import_object_key="ivac_explorations/v1/metadata/ivac_explorations.xml",
    )

    service = MagicMock()
    service.production_bucket = "lacos-production"
    service.resolve_pid_to_s3.return_value = SimpleNamespace(
        s3_bucket="lacos-ingest",
        s3_key=metadata_key,
    )
    service.generate_presigned_url.return_value = "https://example.test/collection-metadata"

    def head_object(**kwargs):
        bucket = kwargs["Bucket"]
        key = kwargs["Key"]
        if bucket == "lacos-ingest":
            raise _not_found_error()
        assert bucket == "lacos-production"
        assert key == metadata_key
        return {}

    service.s3_client.head_object.side_effect = head_object

    result = resolve_collection_metadata_to_presigned(service, metadata_file, collection)

    assert result == {
        "bucket": "lacos-production",
        "key": metadata_key,
        "url": "https://example.test/collection-metadata",
    }
    service.register_s3_location.assert_called_once_with(
        metadata_file,
        "lacos-production",
        metadata_key,
        pid_url="hdl:11341/0000-0000-0000-DDDD",
        fetch_metadata=False,
    )


def test_load_xml_preview_returns_pretty_xml_without_declaration():
    service = MagicMock()
    body = MagicMock()
    body.read.return_value = b'<?xml version="1.0" encoding="UTF-8"?><root><child>value</child></root>'
    service.s3_client.get_object.return_value = {"Body": body}

    preview = load_xml_preview(service, "bucket-a", "path/file.imdi")

    assert preview is not None
    assert not preview.startswith("<?xml")
    assert "<root>" in preview
    assert "<child>value</child>" in preview


def test_load_xml_preview_returns_none_when_object_is_too_large():
    service = MagicMock()
    body = MagicMock()
    body.read.return_value = b"<root>" + (b"a" * 32) + b"</root>"
    service.s3_client.get_object.return_value = {"Body": body}

    preview = load_xml_preview(
        service,
        "bucket-a",
        "path/file.xml",
        max_preview_bytes=8,
    )

    assert preview is None


def test_load_xml_preview_returns_none_on_s3_error():
    service = MagicMock()
    service.s3_client.get_object.side_effect = RuntimeError("s3 unavailable")

    preview = load_xml_preview(service, "bucket-a", "path/file.xml")

    assert preview is None


def test_load_markdown_preview_sanitizes_active_content():
    service = MagicMock()
    body = MagicMock()
    body.read.return_value = b'[safe](https://example.com) [bad](javascript:alert(1)) <script>alert(1)</script>'
    service.s3_client.get_object.return_value = {"Body": body}

    preview = load_markdown_preview(service, "bucket-a", "path/file.md")

    assert preview is not None
    assert "javascript:" not in preview
    assert "<script" not in preview
