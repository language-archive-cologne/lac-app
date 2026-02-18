from __future__ import annotations

import pytest

from lacos.blam.models import Bundle, Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_publication_info import (
    BundleContributor,
    BundleContributorName,
    BundleCreator,
    BundlePublicationInfo,
)
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionContributor,
    CollectionCreator,
    CollectionPublicationInfo,
)
from lacos.explorer.search import search_archives
from lacos.explorer.search_indexing import (
    rebuild_all_search_vectors,
    update_bundle_search_vector,
    update_collection_search_vector,
)


def _create_collection(identifier: str, title: str) -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Cologne",
        country_name="Germany",
        country_code="DE",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"CID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=f"Description for {title}",
        location=location,
        version="1.0",
    )
    return collection


def _create_bundle(identifier: str, title: str, collection: Collection) -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Accra",
        country_name="Ghana",
        country_code="GH",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"BID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=f"Description for {title}",
        location=location,
        version="1.0",
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    return bundle


@pytest.mark.django_db
def test_simple_search_matches_collection_creator_and_contributor_with_stored_vectors():
    collection = _create_collection("COL-PEOPLE-001", "Collection People")
    publication_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    publication_info.creators.add(
        CollectionCreator.objects.create(
            family_name="Lalinde",
            given_name="Miranda",
        )
    )
    publication_info.contributors.add(
        CollectionContributor.objects.create(
            family_name="Santos",
            given_name="Welton",
            contributor_display_name="Welton Santos",
            role="Field consultant",
        )
    )

    rebuild_all_search_vectors()

    creator_results = search_archives("Miranda", use_stored_vectors=True)
    creator_match = next(
        result
        for result in creator_results
        if result.kind == "collection" and result.object_id == str(collection.pk)
    )
    assert "creator" in creator_match.matched_fields

    contributor_results = search_archives("consultant", use_stored_vectors=True)
    contributor_match = next(
        result
        for result in contributor_results
        if result.kind == "collection" and result.object_id == str(collection.pk)
    )
    assert "contributor" in contributor_match.matched_fields


@pytest.mark.django_db
def test_simple_search_matches_bundle_creator_and_contributor_with_stored_vectors():
    parent_collection = _create_collection("COL-PEOPLE-002", "Parent Collection")
    bundle = _create_bundle("BND-PEOPLE-001", "Bundle People", parent_collection)
    publication_info = BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2024,
        data_provider="LAC",
        identifier="hdl:test/BND-PEOPLE-001",
        identifier_type="HANDLE",
    )
    publication_info.creators.add(
        BundleCreator.objects.create(
            family_name="Lalinde",
            given_name="Miranda",
        )
    )
    contributor_name = BundleContributorName.objects.create(
        contributor_family_name="Santos",
        contributor_given_name="Welton",
    )
    publication_info.contributors.add(
        BundleContributor.objects.create(
            contributor_name=contributor_name,
            family_name="Santos",
            given_name="Welton",
            role="Field consultant",
        )
    )

    rebuild_all_search_vectors()

    creator_results = search_archives("Miranda", use_stored_vectors=True)
    creator_match = next(
        result
        for result in creator_results
        if result.kind == "bundle" and result.object_id == str(bundle.pk)
    )
    assert "creator" in creator_match.matched_fields

    contributor_results = search_archives("Welton", use_stored_vectors=True)
    contributor_match = next(
        result
        for result in contributor_results
        if result.kind == "bundle" and result.object_id == str(bundle.pk)
    )
    assert "contributor" in contributor_match.matched_fields


@pytest.mark.django_db
def test_advanced_collection_search_matches_creator_and_contributor(client):
    matching_collection = _create_collection("COL-PEOPLE-003", "Collection Match")
    other_collection = _create_collection("COL-PEOPLE-004", "Collection Other")

    matching_pub = CollectionPublicationInfo.objects.create(
        collection=matching_collection,
        publication_year=2024,
        data_provider="LAC",
    )
    matching_pub.creators.add(
        CollectionCreator.objects.create(
            family_name="Lalinde",
            given_name="Miranda",
        )
    )
    matching_pub.contributors.add(
        CollectionContributor.objects.create(
            family_name="Santos",
            given_name="Welton",
            contributor_display_name="Welton Santos",
            role="Field consultant",
        )
    )

    CollectionPublicationInfo.objects.create(
        collection=other_collection,
        publication_year=2024,
        data_provider="LAC",
    )

    update_collection_search_vector(matching_collection)
    update_collection_search_vector(other_collection)

    creator_response = client.get("/search/", {"q": "Miranda"})
    assert creator_response.status_code == 200
    creator_identifiers = {obj.identifier for obj in creator_response.context["collections"]}
    assert "COL-PEOPLE-003" in creator_identifiers
    assert "COL-PEOPLE-004" not in creator_identifiers
    assert "Creator" in creator_response.content.decode("utf-8")

    contributor_response = client.get("/search/", {"q": "Welton"})
    assert contributor_response.status_code == 200
    contributor_identifiers = {obj.identifier for obj in contributor_response.context["collections"]}
    assert "COL-PEOPLE-003" in contributor_identifiers
    assert "COL-PEOPLE-004" not in contributor_identifiers
    assert "Contributor" in contributor_response.content.decode("utf-8")


@pytest.mark.django_db
def test_advanced_bundle_search_matches_creator_and_contributor(client):
    parent_collection = _create_collection("COL-PEOPLE-005", "Bundle Parent")
    matching_bundle = _create_bundle("BND-PEOPLE-002", "Bundle Match", parent_collection)
    other_bundle = _create_bundle("BND-PEOPLE-003", "Bundle Other", parent_collection)

    matching_pub = BundlePublicationInfo.objects.create(
        bundle=matching_bundle,
        publication_year=2024,
        data_provider="LAC",
        identifier="hdl:test/BND-PEOPLE-002",
        identifier_type="HANDLE",
    )
    matching_pub.creators.add(
        BundleCreator.objects.create(
            family_name="Lalinde",
            given_name="Miranda",
        )
    )
    contributor_name = BundleContributorName.objects.create(
        contributor_family_name="Santos",
        contributor_given_name="Welton",
    )
    matching_pub.contributors.add(
        BundleContributor.objects.create(
            contributor_name=contributor_name,
            family_name="Santos",
            given_name="Welton",
            role="Field consultant",
        )
    )

    BundlePublicationInfo.objects.create(
        bundle=other_bundle,
        publication_year=2024,
        data_provider="LAC",
        identifier="hdl:test/BND-PEOPLE-003",
        identifier_type="HANDLE",
    )

    update_bundle_search_vector(matching_bundle)
    update_bundle_search_vector(other_bundle)

    creator_response = client.get("/search/bundles/", {"q": "Miranda"})
    assert creator_response.status_code == 200
    creator_identifiers = {obj.identifier for obj in creator_response.context["bundles"]}
    assert "BND-PEOPLE-002" in creator_identifiers
    assert "BND-PEOPLE-003" not in creator_identifiers
    assert "Creator" in creator_response.content.decode("utf-8")

    contributor_response = client.get("/search/bundles/", {"q": "Welton"})
    assert contributor_response.status_code == 200
    contributor_identifiers = {obj.identifier for obj in contributor_response.context["bundles"]}
    assert "BND-PEOPLE-002" in contributor_identifiers
    assert "BND-PEOPLE-003" not in contributor_identifiers
    assert "Contributor" in contributor_response.content.decode("utf-8")
