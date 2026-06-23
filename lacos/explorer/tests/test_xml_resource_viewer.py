from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.explorer.services.imdi_access import build_imdi_access_token
from lacos.explorer.views.bundles import ResourceAccessView


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


class _FakeDerivativeS3Client:
    def __init__(self, existing_keys):
        self.existing_keys = set(existing_keys)

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.existing_keys:
            raise RuntimeError("missing sidecar")
        return {}


def test_resource_modal_htmx_fragments_do_not_include_inline_scripts():
    xml_page = render_to_string(
        "explorer/partials/resource_modal_content.html",
        {
            "resource_name": "metadata.xml",
            "media_type": "xml",
            "mime_type": "application/xml",
            "preview_url": "https://example.test/metadata.xml",
            "download_url": "https://example.test/download",
            "xml_content": "<METATRANSCRIPT/>",
        },
    )
    video_page = render_to_string(
        "explorer/partials/resource_modal_content.html",
        {
            "resource_name": "interview.mp4",
            "media_type": "video",
            "mime_type": "video/mp4",
            "source_mime_type": "video/mp4",
            "stream_url": "https://example.test/interview.mp4",
            "download_url": "https://example.test/download",
            "subtitle_url": "https://example.test/interview.srt",
        },
    )

    assert "<script" not in xml_page.lower()
    assert "<script" not in video_page.lower()
    assert 'id="resource-xml-content"' in xml_page
    assert 'data-subtitle-url="https://example.test/interview.srt"' in video_page


def test_resource_modal_handle_copy_uses_resolver_url():
    page = render_to_string(
        "explorer/partials/resource_modal_content.html",
        {
            "resource": SimpleNamespace(
                file_pid="hdl:11341/0000-0000-0000-3235",
            ),
            "resource_name": "resource.bin",
            "media_type": None,
            "mime_type": "application/octet-stream",
            "preview_url": "https://example.test/resource.bin",
            "download_url": "https://example.test/download",
        },
    )

    assert "hdl:11341/0000-0000-0000-3235" in page
    assert 'data-copy-text="https://hdl.handle.net/11341/0000-0000-0000-3235"' in page


def test_elan_annotation_data_times_are_not_localized():
    context = {
        "resource_name": "session.eaf",
        "media_type": "elan",
        "mime_type": "text/x-eaf+xml",
        "source_mime_type": "text/x-eaf+xml",
        "download_url": "https://example.test/download",
        "peaks_url": None,
        "player_mode": "simple",
        "elan_context": {
            "audio_url": "https://example.test/session.wav",
            "audio_file_name": "session.wav",
            "tier_headers": ["Transcription"],
            "annotations": [
                {
                    "start": 153.74,
                    "end": 154.67,
                    "value": "bur mina",
                    "ordered_tiers": [
                        {"name": "Transcription", "value": "bur mina"},
                    ],
                },
            ],
        },
    }

    with translation.override("de"):
        page = render_to_string(
            "explorer/partials/resource_modal_content.html",
            context,
        )

    assert 'data-annotation-start="153.740"' in page
    assert 'data-annotation-end="154.670"' in page
    assert 'data-annotation-start="153,740"' not in page
    assert 'data-annotation-end="154,670"' not in page


@pytest.mark.django_db
def test_elan_context_prefers_fallback_audio_with_sidecars(monkeypatch):
    bundle = Bundle.objects.create(identifier="hdl:test/bundle-elan-sidecars")
    resources = BundleResources.objects.create(bundle=bundle)
    elan = WrittenResource.objects.create(
        file_pid="hdl:test/elan",
        file_name="quis_focus_sp.eaf",
        mime_type="text/xml",
    )
    external_speaker_audio = MediaResource.objects.create(
        file_pid="hdl:test/extsp",
        file_name="quis_focus_sp_extsp.wav",
        mime_type="audio/x-wav",
    )
    internal_speaker_audio = MediaResource.objects.create(
        file_pid="hdl:test/int",
        file_name="quis_focus_sp_int.wav",
        mime_type="audio/x-wav",
    )
    resources.bundle_written_resources.add(elan)
    resources.bundle_media_resources.add(external_speaker_audio, internal_speaker_audio)

    audio_keys = {
        external_speaker_audio.id: (
            "collection/bundle/v1/content/quis_focus_sp_extsp.wav"
        ),
        internal_speaker_audio.id: "collection/bundle/v1/content/quis_focus_sp_int.wav",
    }
    internal_pitch_key = (
        "collection/bundle/v1/derivatives/quis_focus_sp_int.wav.pitch.bin"
    )
    internal_peaks_key = (
        "collection/bundle/v1/derivatives/quis_focus_sp_int.wav.peaks.json"
    )
    internal_spectrogram_key = (
        "collection/bundle/v1/derivatives/quis_focus_sp_int.wav.spectrogram.bin"
    )
    service = SimpleNamespace(
        s3_client=_FakeDerivativeS3Client(
            {internal_peaks_key, internal_pitch_key, internal_spectrogram_key},
        ),
        generate_presigned_url=lambda _bucket, key: f"https://example.test/{key}",
    )

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.parse_elan_document",
        lambda *_args, **_kwargs: {
            "annotations": [],
            "media_files": [],
            "tier_headers": [],
        },
    )

    def fake_resolve(_service, resource, *_args, **_kwargs):
        key = audio_keys.get(resource.id)
        if key is None:
            return None
        return {
            "bucket": "bucket-a",
            "key": key,
            "url": f"https://example.test/{resource.file_name}",
        }

    monkeypatch.setattr(
        "lacos.explorer.views.bundles.resolve_resource_to_presigned",
        fake_resolve,
    )

    context = ResourceAccessView()._build_elan_context(
        service,
        bundle,
        elan,
        collection_for_path=None,
        bucket_name="bucket-a",
        object_key="collection/bundle/v1/content/quis_focus_sp.eaf",
    )

    assert context["audio_file_name"] == "quis_focus_sp_int.wav"
    assert context["audio_key"] == audio_keys[internal_speaker_audio.id]


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
    assert "data-access-token=" in page
    assert "data-bucket=" not in page


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
    assert "data-access-token=" in page
    assert "data-bucket=" not in page


@pytest.mark.django_db
def test_collection_video_resource_renders_matching_subtitle_url(client, monkeypatch):
    collection = Collection.objects.create(identifier="hdl:test/collection-video-resource")
    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    video_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/collection-video-file",
        file_name="interview.mp4",
        mime_type="video/mp4",
        file_description="Interview video",
    )
    structural_info.additional_metadata_files.add(video_file)

    class DummyService:
        def resolve_pid_to_s3(self, _pid):
            return None

        def generate_presigned_url(self, _bucket, _key, response_headers=None):
            if response_headers:
                return "https://example.test/download"
            return "https://example.test/interview.mp4"

    monkeypatch.setattr(
        "lacos.explorer.views.collections.ResourceMappingService",
        lambda *args, **kwargs: DummyService(),
    )
    monkeypatch.setattr(
        "lacos.explorer.views.collections.resolve_collection_metadata_to_presigned",
        lambda *_args, **_kwargs: {
            "bucket": "bucket-a",
            "key": "path/interview.mp4",
            "url": "https://example.test/interview.mp4",
        },
    )
    monkeypatch.setattr(
        "lacos.explorer.views.collections.find_subtitle_for_collection_video",
        lambda *_args, **_kwargs: "https://example.test/interview.srt",
    )

    response = client.get(
        reverse(
            "explorer:collection_resource_by_handle",
            kwargs={
                "handle": collection.identifier,
                "resource_id": video_file.file_pid,
            },
        ),
        {"action": "play"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'data-subtitle-url="https://example.test/interview.srt"' in page


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


@pytest.mark.django_db
def test_imdi_xml_view_rejects_requests_without_signed_token(client):
    response = client.get(reverse("explorer:imdi_xml"), {"bucket": "bucket-a", "key": "path/file.imdi"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_imdi_xml_view_allows_signed_root_access(client, monkeypatch):
    class DummyStorage:
        def read_imdi_file(self, bucket, key):
            assert bucket == "bucket-a"
            assert key == "collection-a/metadata/file.imdi"
            return b"<METATRANSCRIPT/>"

    monkeypatch.setattr("lacos.explorer.views.imdi._get_storage_service", lambda: DummyStorage())

    token = build_imdi_access_token(
        bucket="bucket-a",
        root_key="collection-a/metadata/file.imdi",
    )
    response = client.get(reverse("explorer:imdi_xml"), {"token": token})

    assert response.status_code == 200
    assert response.content == b"<METATRANSCRIPT/>"


@pytest.mark.django_db
def test_imdi_xml_view_rejects_signed_requests_outside_allowed_prefix(client, monkeypatch):
    class DummyStorage:
        def read_imdi_file(self, bucket, key):  # pragma: no cover - should not be called
            raise AssertionError(f"Unexpected storage read for {bucket}/{key}")

    monkeypatch.setattr("lacos.explorer.views.imdi._get_storage_service", lambda: DummyStorage())

    token = build_imdi_access_token(
        bucket="bucket-a",
        root_key="collection-a/metadata/file.imdi",
    )
    response = client.get(
        reverse("explorer:imdi_xml"),
        {"token": token, "key": "other-collection/metadata/file.imdi"},
    )

    assert response.status_code == 403
