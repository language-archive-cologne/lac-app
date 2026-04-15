from types import SimpleNamespace

import pytest
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    WrittenResource,
    BundleStructuralInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)


class _FakeS3Body:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self, payload: bytes):
        self._payload = payload

    def get_object(self, **_kwargs):
        return {"Body": _FakeS3Body(self._payload)}


@pytest.mark.django_db
def test_bundle_imdi_resource_renders_imdi_modal_for_htmx_view(client, monkeypatch):
    collection = Collection.objects.create(identifier="hdl:test/collection-imdi-bundle")
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-imdi-resource")
    structural_info = BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/bundle-imdi-file",
        file_name="Wooinap_family_situation.imdi",
        mime_type="application/octet-stream",
        file_description="Bundle IMDI metadata",
    )
    structural_info.additional_metadata_files.add(metadata_file)

    class DummyService:
        s3_client = _FakeS3Client(b"<METATRANSCRIPT/>")

        def generate_presigned_url(self, _bucket, _key, response_headers=None):
            if response_headers:
                return "https://example.test/download"
            return "https://example.test/preview"

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ResourceMappingService",
        lambda *args, **kwargs: DummyService(),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.resolve_resource_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "bucket-a",
            "key": "path/Wooinap_family_situation.imdi",
            "url": "https://example.test/preview",
        },
    )

    response = client.get(
        reverse(
            "explorer:resource_access",
            kwargs={"bundle_id": bundle.pk, "resource_id": metadata_file.pk},
        ),
        {"action": "view"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'data-viewer-type="imdi"' in page
    assert "data-imdi-viewer" in page


@pytest.mark.django_db
def test_collection_imdi_resource_renders_imdi_modal_for_htmx_view(client, monkeypatch):
    collection = Collection.objects.create(identifier="hdl:test/collection-imdi-resource")
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/collection-imdi-file",
        file_name="collection_metadata.imdi",
        mime_type="application/octet-stream",
        file_description="Collection IMDI metadata",
    )
    structural_info.additional_metadata_files.add(metadata_file)

    class DummyService:
        s3_client = _FakeS3Client(b"<METATRANSCRIPT/>")

        def resolve_pid_to_s3(self, _pid):
            return None

        def generate_presigned_url(self, _bucket, _key, response_headers=None):
            if response_headers:
                return "https://example.test/download"
            return "https://example.test/preview"

    monkeypatch.setattr(
        "lacos.explorer.views.collections.ResourceMappingService",
        lambda *args, **kwargs: DummyService(),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.collections.resolve_collection_metadata_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "bucket-a",
            "key": "path/collection_metadata.imdi",
            "url": "https://example.test/preview",
        },
    )

    response = client.get(
        reverse(
            "explorer:collection_resource_by_handle",
            kwargs={
                "handle": collection.identifier,
                "resource_id": metadata_file.file_pid,
            },
        ),
        {"action": "view"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'data-viewer-type="imdi"' in page
    assert "data-imdi-viewer" in page


@pytest.mark.django_db
def test_collection_imdi_resource_uses_metadata_fallback_when_pid_mapping_missing(client, monkeypatch):
    collection = Collection.objects.create(identifier="hdl:test/collection-imdi-fallback")
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/collection-imdi-fallback-file",
        file_name="collection_fallback.imdi",
        mime_type="application/octet-stream",
        file_description="Collection IMDI metadata",
    )
    structural_info.additional_metadata_files.add(metadata_file)

    class DummyService:
        s3_client = _FakeS3Client(b"<METATRANSCRIPT/>")

        def resolve_pid_to_s3(self, _pid):
            return None

        def generate_presigned_url(self, _bucket, _key, response_headers=None):
            if response_headers:
                return "https://example.test/download"
            return "https://example.test/preview"

    def build_service(*, skip_bucket_check=False):
        assert skip_bucket_check is True
        return DummyService()

    monkeypatch.setattr(
        "lacos.explorer.views.collections.ResourceMappingService",
        build_service,
    )
    monkeypatch.setattr(
        "lacos.explorer.views.collections.resolve_collection_metadata_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "bucket-a",
            "key": "path/collection_fallback.imdi",
            "url": "https://example.test/preview",
        },
    )

    response = client.get(
        reverse(
            "explorer:collection_resource_by_handle",
            kwargs={
                "handle": collection.identifier,
                "resource_id": metadata_file.file_pid,
            },
        ),
        {"action": "view"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'data-viewer-type="imdi"' in page


@pytest.mark.django_db
def test_bundle_elan_resource_handles_storage_fetch_failure(client, monkeypatch):
    collection = Collection.objects.create(identifier="hdl:test/collection-elan-bundle")
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-elan-resource")
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    elan_resource = WrittenResource.objects.create(
        file_pid="hdl:test/bundle-elan-file",
        file_name="zag_mam_20160720_3.eaf",
        mime_type="text/x-eaf+xml",
        file_description="ELAN annotation",
    )
    bundle_resources.bundle_written_resources.add(elan_resource)

    class ExplodingS3Client:
        def get_object(self, **_kwargs):
            raise RuntimeError("Could not connect to the endpoint URL")

    class DummyService:
        s3_client = ExplodingS3Client()

        def generate_presigned_url(self, _bucket, _key, response_headers=None):
            if response_headers:
                return "https://example.test/download"
            return "https://example.test/preview"

        def resolve_pid_to_s3(self, _pid):
            return None

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ResourceMappingService",
        lambda *args, **kwargs: DummyService(),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.resolve_resource_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "lacos-production",
            "key": "beria/adjectives_10/v1/content/zag_mam_20160720_3.eaf",
            "url": "https://example.test/preview",
        },
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ACLEvaluationService.evaluate",
        lambda *_args, **_kwargs: SimpleNamespace(allowed=True),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.bundles.ACLEvaluationService.enforcement_enabled",
        True,
        raising=False,
    )

    response = client.get(
        reverse(
            "explorer:resource_access",
            kwargs={"bundle_id": bundle.pk, "resource_id": elan_resource.pk},
        ),
        {"action": "play"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'data-viewer-type="elan"' in page
    assert "No linked audio track found for this ELAN file." in page
