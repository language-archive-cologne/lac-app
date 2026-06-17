import pytest
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.explorer.models import BundleFileTypeFacet


@pytest.mark.django_db
def test_collection_detail_htmx_bundle_per_page_50_returns_table_partial(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-page-size")
    for index in range(55):
        bundle = Bundle.objects.create(identifier=f"bundle-page-size-{index:02d}")
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.identifier},
        ),
        {"bundle_per_page": "50"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="collection-bundles-table",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<!DOCTYPE html>" not in page
    assert page.count("data-bundle-row") == 50
    assert "1–50" in page
    assert "55 bundles" in page
    assert '<option value="50" selected' in page


@pytest.mark.django_db
def test_collection_detail_bundle_per_page_select_triggers_on_change(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-page-control")
    for index in range(11):
        bundle = Bundle.objects.create(identifier=f"bundle-page-control-{index:02d}")
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.identifier},
        ),
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'name="bundle_per_page"' in page
    assert 'hx-trigger="change"' in page
    assert "Search bundles" in page
    assert "Title, description, handle, filename" in page


@pytest.mark.django_db
def test_collection_detail_can_filter_bundles_by_file_type(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-file-type")
    wav_bundle = Bundle.objects.create(identifier="bundle-with-wav")
    pdf_bundle = Bundle.objects.create(identifier="bundle-with-pdf")
    for bundle in (wav_bundle, pdf_bundle):
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )
    BundleFileTypeFacet.objects.create(
        bundle=wav_bundle,
        collection=collection,
        file_type="wav",
    )
    BundleFileTypeFacet.objects.create(
        bundle=pdf_bundle,
        collection=collection,
        file_type="pdf",
    )

    response = client.get(
        reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
        {"bundle_file_type": "wav"},
    )

    assert response.status_code == 200
    assert response.context["bundle_file_type"] == "wav"
    identifiers = [
        ctx["bundle"].identifier for ctx in response.context["bundle_contexts"]
    ]
    assert identifiers == [wav_bundle.identifier]
    page = response.content.decode("utf-8")
    assert 'name="bundle_file_type"' in page
    assert '<option value="wav" selected' in page
    assert "WAV (1)" in page
    assert "PDF (1)" in page
    assert "Contains format" in page
    assert "Any format" in page


@pytest.mark.django_db
def test_collection_detail_bundle_search_includes_resource_file_names(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-filename-search")
    matching_bundle = Bundle.objects.create(identifier="bundle-with-matching-file")
    other_bundle = Bundle.objects.create(identifier="bundle-with-other-file")
    for bundle in (matching_bundle, other_bundle):
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )
    resources = BundleResources.objects.create(bundle=matching_bundle)
    audio = MediaResource.objects.create(
        file_name="morning-story.wav",
        file_pid="https://hdl.handle.net/morning-story",
        mime_type="audio/wav",
        file_length="10",
    )
    resources.bundle_media_resources.add(audio)

    response = client.get(
        reverse("explorer:collection_detail", kwargs={"pk": collection.pk}),
        {"bundle_search": "morning-story"},
    )

    assert response.status_code == 200
    identifiers = [
        ctx["bundle"].identifier for ctx in response.context["bundle_contexts"]
    ]
    assert identifiers == [matching_bundle.identifier]


@pytest.mark.django_db
def test_collection_detail_htmx_file_type_filter_returns_table_partial(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-file-type-htmx")
    wav_bundle = Bundle.objects.create(identifier="bundle-htmx-wav")
    pdf_bundle = Bundle.objects.create(identifier="bundle-htmx-pdf")
    for bundle in (wav_bundle, pdf_bundle):
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )
    BundleFileTypeFacet.objects.create(
        bundle=wav_bundle,
        collection=collection,
        file_type="wav",
    )
    BundleFileTypeFacet.objects.create(
        bundle=pdf_bundle,
        collection=collection,
        file_type="pdf",
    )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.identifier},
        ),
        {"bundle_file_type": "pdf"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="collection-bundles-table",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<!DOCTYPE html>" not in page
    assert pdf_bundle.identifier in page
    assert wav_bundle.identifier not in page
