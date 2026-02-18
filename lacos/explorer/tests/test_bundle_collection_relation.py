from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(identifier: str, title: str) -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=title,
        description=f"{title} description",
        version="1.0",
        location=location,
    )
    return collection


def _create_bundle(
    identifier: str,
    title: str,
    *,
    collection: Collection | None = None,
) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Test Location",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=title,
        description=f"{title} description",
        version="1.0",
        location=location,
    )
    if collection is not None:
        BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


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
def test_bundle_search_results_show_parent_collection(client):
    collection = _create_collection("COL-REL-SEARCH", "Parent Collection Title")
    _create_bundle("BND-REL-SEARCH", "Tree Bundle", collection=collection)
    rebuild_all_search_vectors()

    response = client.get(reverse("explorer:collection_list"), {"q": "Tree"})

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Part of" in page
    assert "Parent Collection Title" in page
    assert reverse("explorer:collection_detail_by_handle", kwargs={"handle": collection.identifier}) in page


@pytest.mark.django_db
def test_bundle_faceted_table_shows_parent_collection(client):
    collection = _create_collection("COL-REL-FACET", "Facet Parent Collection")
    _create_bundle("BND-REL-FACET", "Facet Bundle", collection=collection)

    response = client.get(reverse("bundle_faceted_search"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Part of" in page
    assert "Facet Parent Collection" in page
    assert reverse("explorer:collection_detail_by_handle", kwargs={"handle": collection.identifier}) in page


@pytest.mark.django_db
def test_bundle_detail_shows_explicit_parent_collection(client):
    collection = _create_collection("COL-REL-DETAIL", "Bundle Parent Title")
    bundle = _create_bundle("BND-REL-DETAIL", "Bundle Relation", collection=collection)
    _allow_anonymous_read(bundle)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Back to Collection" in page
    assert "Bundle Parent Title" in page
    assert "Part of" in page
    assert "Bundle Parent Title" in page


@pytest.mark.django_db
def test_bundle_detail_without_parent_keeps_generic_back_link(client):
    bundle = _create_bundle("BND-NO-PARENT", "Bundle Without Parent")
    _allow_anonymous_read(bundle)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Back to Collections" in page
    assert "Back to Collection:" not in page
