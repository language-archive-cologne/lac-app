import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(identifier: str = "discoverability-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Discoverability Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Discoverability Collection",
        description="Discoverability Collection Description",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection: Collection, identifier: str = "discoverability-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Discoverability Bundle Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Discoverability Bundle",
        description="Discoverability Bundle Description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _store_acl(obj, rules):
    ct = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.create(
        content_type=ct,
        object_id=obj.pk,
        ACL_file_bucket="test-bucket",
        ACL_file_key="test/key",
        permissions_data=rules,
    )


@pytest.mark.django_db
def test_sitemap_includes_restricted_metadata_pages(client):
    collection = _create_collection("discoverability-restricted-collection")
    bundle = _create_bundle(collection, "discoverability-restricted-bundle")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    response = client.get(reverse("django.contrib.sitemaps.views.sitemap"))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert collection.handle_path in body
    assert bundle.handle_path in body


@pytest.mark.django_db
def test_oai_list_identifiers_includes_restricted_collection_metadata(client):
    collection = _create_collection("discoverability-oai-collection")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListIdentifiers", "metadataPrefix": "oai_dc", "set": "collections"},
    )

    assert response.status_code == 200
    assert f"oai:lacos:{collection.identifier}" in response.content.decode("utf-8")
