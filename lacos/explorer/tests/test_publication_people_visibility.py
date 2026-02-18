from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_general_info import BundleLocation
from lacos.blam.models.bundle.bundle_publication_info import BundleContributor
from lacos.blam.models.bundle.bundle_publication_info import BundleContributorName
from lacos.blam.models.bundle.bundle_publication_info import BundleCreator
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionLocation
from lacos.blam.models.collection.collection_publication_info import CollectionContributor
from lacos.blam.models.collection.collection_publication_info import CollectionCreator
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
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


def _create_bundle(identifier: str, title: str, collection: Collection) -> Bundle:
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
def test_collection_detail_shows_creators_and_contributors(client):
    collection = _create_collection("COL-PUB-PEOPLE", "Collection Publication People")
    publication = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    publication.creators.add(
        CollectionCreator.objects.create(
            family_name="Creator",
            given_name="Alice",
            affiliation="University of Cologne",
        )
    )
    publication.contributors.add(
        CollectionContributor.objects.create(
            family_name="Contributor",
            given_name="Bob",
            contributor_display_name="Bob Contributor",
            role="['Field consultant']",
            affiliation="Archive Team",
            name_identifier="mailto:bob@example.org",
            name_identifier_type="email",
        )
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Creators" in page
    assert "Alice Creator" in page
    assert "Contributors" in page
    assert "Bob Contributor" in page
    assert "Field consultant" in page
    assert "['Field consultant']" not in page
    assert "mailto:bob@example.org" not in page
    assert "Email:" not in page


@pytest.mark.django_db
def test_collection_detail_hides_contributors_when_missing(client):
    collection = _create_collection("COL-PUB-CREATORS", "Collection Creators Only")
    publication = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    publication.creators.add(CollectionCreator.objects.create(family_name="Solo", given_name="Creator"))

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Creators" in page
    assert "Creator Solo" in page
    assert "Contributors" not in page
    assert "See all contributors" not in page


@pytest.mark.django_db
def test_bundle_detail_shows_creators_and_contributors(client):
    collection = _create_collection("COL-BUNDLE-PUB", "Bundle Publication Parent")
    bundle = _create_bundle("BND-PUB-PEOPLE", "Bundle Publication People", collection)
    _allow_anonymous_read(bundle)

    publication = BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2024,
        data_provider="LAC",
        identifier="hdl:test/BND-PUB-PEOPLE",
        identifier_type=IdentifierTypeChoices.HANDLE,
    )
    publication.creators.add(
        BundleCreator.objects.create(
            family_name="Creator",
            given_name="Nora",
            affiliation="University",
        )
    )

    contributor_name = BundleContributorName.objects.create(
        contributor_family_name="Contributor",
        contributor_given_name="Sam",
    )
    publication.contributors.add(
        BundleContributor.objects.create(
            contributor_name=contributor_name,
            family_name="Contributor",
            given_name="Sam",
            role="['Field consultant']",
            affiliation="Field Team",
            name_identifier="mailto:sam@example.org",
            name_identifier_type="email",
        )
    )

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Creators" in page
    assert "Nora Creator" in page
    assert "Contributors" in page
    assert "Sam Contributor" in page
    assert "Field consultant" in page
    assert "['Field consultant']" not in page
    assert "mailto:sam@example.org" not in page
    assert "Email:" not in page
    assert "See all contributors" not in page


@pytest.mark.django_db
def test_bundle_detail_shows_contributors_modal_for_long_lists(client):
    collection = _create_collection("COL-BUNDLE-LONG-CONTRIB", "Bundle Parent Long Contributors")
    bundle = _create_bundle("BND-LONG-CONTRIB", "Bundle Many Contributors", collection)
    _allow_anonymous_read(bundle)

    publication = BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2024,
        data_provider="LAC",
        identifier="hdl:test/BND-LONG-CONTRIB",
        identifier_type=IdentifierTypeChoices.HANDLE,
    )

    for idx in range(1, 6):
        contributor_name = BundleContributorName.objects.create(
            contributor_family_name=f"Contributor{idx}",
            contributor_given_name=f"Name{idx}",
        )
        publication.contributors.add(
            BundleContributor.objects.create(
                contributor_name=contributor_name,
                family_name=f"Contributor{idx}",
                given_name=f"Name{idx}",
                role="['Field consultant']",
            )
        )

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "See all contributors (5)" in page
    assert 'id="bundle-contributors-modal"' in page
    assert "max-h-[70vh] overflow-y-auto" in page
    assert "Name5 Contributor5" in page


@pytest.mark.django_db
def test_collection_detail_shows_contributors_modal_for_long_lists(client):
    collection = _create_collection("COL-PUB-LONG-CONTRIB", "Collection Many Contributors")
    publication = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )

    for idx in range(1, 6):
        publication.contributors.add(
            CollectionContributor.objects.create(
                family_name=f"Contributor{idx}",
                given_name=f"Name{idx}",
                contributor_display_name=f"Name{idx} Contributor{idx}",
                role="['Field consultant']",
            )
        )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "See all contributors (5)" in page
    assert 'id="collection-contributors-modal"' in page
    assert "max-h-[70vh] overflow-y-auto" in page
    assert "Name5 Contributor5" in page


@pytest.mark.django_db
def test_bundle_detail_hides_publication_people_when_missing(client):
    collection = _create_collection("COL-BUNDLE-NO-PUB", "Bundle Parent")
    bundle = _create_bundle("BND-NO-PUB", "Bundle Without Publication", collection)
    _allow_anonymous_read(bundle)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "Creators" not in page
    assert "Contributors" not in page
