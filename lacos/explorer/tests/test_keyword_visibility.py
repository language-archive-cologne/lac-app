from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleKeyword
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionKeyword
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(identifier: str, title: str) -> tuple[Collection, CollectionGeneralInfo]:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=title,
        description=f"{title} description",
        version="1.0",
        location=location,
    )
    return collection, general_info


def _create_bundle(
    identifier: str,
    title: str,
    collection: Collection,
) -> tuple[Bundle, BundleGeneralInfo]:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Test Location",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=title,
        description=f"{title} description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle, general_info


def _allow_anonymous_read(obj) -> None:
    ACLPermissions.objects.update_or_create(
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        defaults={
            "permissions_data": [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}],
            "ACL_file_bucket": "test-bucket",
            "ACL_file_key": "test/key",
        },
    )


@pytest.mark.django_db
def test_collection_list_renders_compact_keywords(client):
    collection, general_info = _create_collection("COL-KW-1", "Keyword Collection")
    _create_collection("COL-KW-2", "No Keyword Collection")
    _create_bundle("BUN-KW-1", "Keyword Bundle", collection)

    long_keyword = "very-long-keyword-value-for-tooltip-checking"
    keyword_values = [long_keyword, "phonology", "documentation", "archive"]
    for value in keyword_values:
        general_info.keywords.add(CollectionKeyword.objects.create(value=value))

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert collection.identifier in page
    assert long_keyword in page
    assert "phonology" in page
    assert "documentation" in page
    assert '+1' in page
    assert 'title="archive"' in page
    assert f'title="{long_keyword}"' in page


@pytest.mark.django_db
def test_collection_detail_shows_keywords_when_present(client):
    collection, general_info = _create_collection("COL-DETAIL-KW", "Collection Detail")
    general_info.keywords.add(CollectionKeyword.objects.create(value="oral history"))
    general_info.keywords.add(CollectionKeyword.objects.create(value="field notes"))

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Keywords" in page
    assert "oral history" in page
    assert "field notes" in page


@pytest.mark.django_db
def test_collection_detail_hides_keywords_when_empty(client):
    collection, _ = _create_collection("COL-DETAIL-NO-KW", "Collection Detail Empty")

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Keywords" not in page


@pytest.mark.django_db
def test_bundle_faceted_list_renders_compact_keywords(client):
    collection, _ = _create_collection("COL-BUNDLE-LIST", "Bundle Parent")
    bundle, general_info = _create_bundle("BND-KW-1", "Bundle Keywords", collection)
    _create_bundle("BND-KW-2", "Bundle No Keywords", collection)

    long_keyword = "bundle-keyword-with-a-long-value-for-tooltip"
    keyword_values = [long_keyword, "audio", "transcription", "metadata"]
    for value in keyword_values:
        general_info.keywords.add(BundleKeyword.objects.create(value=value))

    response = client.get(reverse("bundle_faceted_search"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert bundle.identifier in page
    assert long_keyword in page
    assert "audio" in page
    assert "transcription" in page
    assert '+1' in page
    assert 'title="metadata"' in page
    assert f'title="{long_keyword}"' in page


@pytest.mark.django_db
def test_bundle_detail_shows_keywords_when_present(client):
    collection, _ = _create_collection("COL-BUNDLE-DETAIL", "Bundle Detail Parent")
    bundle, general_info = _create_bundle("BND-DETAIL-KW", "Bundle Detail", collection)
    _allow_anonymous_read(bundle)
    general_info.keywords.add(BundleKeyword.objects.create(value="elicitation"))
    general_info.keywords.add(BundleKeyword.objects.create(value="conversation"))

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Keywords" in page
    assert "elicitation" in page
    assert "conversation" in page


@pytest.mark.django_db
def test_bundle_detail_hides_keywords_when_empty(client):
    collection, _ = _create_collection("COL-BUNDLE-DETAIL-NO-KW", "Bundle Detail Parent Empty")
    bundle, _ = _create_bundle("BND-DETAIL-NO-KW", "Bundle Detail Empty", collection)
    _allow_anonymous_read(bundle)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Keywords" not in page


@pytest.mark.django_db
def test_collection_search_results_render_keywords(client):
    collection, general_info = _create_collection("COL-SEARCH-KW", "Collection Search Keywords")
    general_info.keywords.add(CollectionKeyword.objects.create(value="search-collection-keyword"))
    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "search-collection-keyword"})

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert collection.identifier in page
    assert "search-collection-keyword" in page


@pytest.mark.django_db
def test_bundle_search_results_render_keywords(client):
    collection, _ = _create_collection("COL-SEARCH-BUNDLE", "Bundle Search Parent")
    bundle, general_info = _create_bundle("BND-SEARCH-KW", "Bundle Search Keywords", collection)
    general_info.keywords.add(BundleKeyword.objects.create(value="search-bundle-keyword"))
    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "search-bundle-keyword"})

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert bundle.identifier in page
    assert "search-bundle-keyword" in page
