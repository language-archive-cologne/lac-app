import pytest

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.bundle.bundle_structural_info import BundleResources
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.bundle.bundle_structural_info import MediaResource
from lacos.blam.models.bundle.bundle_structural_info import OtherResource
from lacos.blam.models.bundle.bundle_structural_info import WrittenResource
from lacos.explorer.file_types import file_type_for_resource
from lacos.explorer.models import BundleFileTypeFacet
from lacos.explorer.services.file_type_facets import refresh_bundle_file_type_facets


def _create_bundle_with_collection() -> tuple[Bundle, Collection]:
    collection = Collection.objects.create(identifier="collection-1")
    bundle = Bundle.objects.create(identifier="bundle-1")
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    return bundle, collection


@pytest.mark.parametrize(
    ("mime_type", "file_name", "expected"),
    [
        ("audio/wav", "speech.wav", "wav"),
        ("audio/mpeg", "song.mp3", "mp3"),
        ("video/quicktime", "recording.mov", "mov"),
        ("video/mp4", "recording.mp4", "mp4"),
        ("image/jpeg", "photo.jpg", "jpg"),
        ("application/pdf", "transcript.pdf", "pdf"),
        ("text/xml", "annotation.eaf", "eaf"),
        ("application/xml", "metadata.xml", "xml"),
        ("application/cmdi+xml", "metadata.cmdi", "cmdi"),
        ("text/plain", "annotation.textgrid", "textgrid"),
        ("text/plain", "conversation.cha", "cha"),
        ("text/plain", "subtitles.vtt", "vtt"),
        ("", "notes.txt", "txt"),
        ("audio/wav", "", "wav"),
        ("audio/x-wav", "", "wav"),
        ("audio/mpeg", "", "mp3"),
        ("video/quicktime", "", "mov"),
        ("image/jpeg", "", "jpg"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "",
            "docx",
        ),
        ("application/msword", "", "doc"),
        ("application/octet-stream", "archive.unknown", None),
        ("audio/x-custom", "", None),
    ],
)
def test_file_type_for_resource(mime_type, file_name, expected):
    assert file_type_for_resource(mime_type, file_name) == expected


@pytest.mark.django_db
def test_refresh_bundle_file_type_facets_creates_distinct_rows():
    bundle, collection = _create_bundle_with_collection()
    expected_count = 4
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    wav = MediaResource.objects.create(
        file_name="speech.wav",
        file_pid="https://hdl.handle.net/audio",
        mime_type="audio/wav",
        file_length="10",
    )
    duplicate_audio = MediaResource.objects.create(
        file_name="speech-copy.wav",
        file_pid="https://hdl.handle.net/audio-copy",
        mime_type="audio/wav",
        file_length="10",
    )
    mp3 = MediaResource.objects.create(
        file_name="speech.mp3",
        file_pid="https://hdl.handle.net/audio-mp3",
        mime_type="audio/mpeg",
        file_length="10",
    )
    elan = WrittenResource.objects.create(
        file_name="annotation.eaf",
        file_pid="https://hdl.handle.net/annotation",
        mime_type="text/xml",
    )
    document = OtherResource.objects.create(
        file_name="transcript.pdf",
        file_pid="https://hdl.handle.net/pdf",
        mime_type="application/pdf",
    )
    unknown = OtherResource.objects.create(
        file_name="archive.unknown",
        file_pid="https://hdl.handle.net/unknown",
        mime_type="application/octet-stream",
    )
    bundle_resources.bundle_media_resources.add(wav, duplicate_audio, mp3)
    bundle_resources.bundle_written_resources.add(elan)
    bundle_resources.bundle_other_resources.add(document, unknown)

    count = refresh_bundle_file_type_facets(bundle)

    assert count == expected_count
    assert set(
        BundleFileTypeFacet.objects.filter(bundle=bundle).values_list(
            "collection",
            "file_type",
        ),
    ) == {
        (collection.id, "eaf"),
        (collection.id, "mp3"),
        (collection.id, "pdf"),
        (collection.id, "wav"),
    }


@pytest.mark.django_db
def test_refresh_bundle_file_type_facets_removes_stale_rows():
    bundle, collection = _create_bundle_with_collection()
    BundleFileTypeFacet.objects.create(
        bundle=bundle,
        collection=collection,
        file_type="audio",
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    document = OtherResource.objects.create(
        file_name="transcript.pdf",
        file_pid="https://hdl.handle.net/pdf",
        mime_type="application/pdf",
    )
    bundle_resources.bundle_other_resources.add(document)

    count = refresh_bundle_file_type_facets(bundle)

    assert count == 1
    assert list(
        BundleFileTypeFacet.objects.filter(bundle=bundle).values_list(
            "file_type",
            flat=True,
        ),
    ) == ["pdf"]


@pytest.mark.django_db
def test_refresh_bundle_file_type_facets_clears_rows_without_collection():
    bundle = Bundle.objects.create(identifier="bundle-without-collection")
    collection = Collection.objects.create(identifier="old-collection")
    BundleFileTypeFacet.objects.create(
        bundle=bundle,
        collection=collection,
        file_type="audio",
    )

    count = refresh_bundle_file_type_facets(bundle)

    assert count == 0
    assert not BundleFileTypeFacet.objects.filter(bundle=bundle).exists()
