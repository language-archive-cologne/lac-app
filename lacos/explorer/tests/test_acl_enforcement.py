import pytest
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleAdditionalMetadataFile, BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.storage.constants import WAC_AUTHENTICATED_AGENT
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(identifier: str = "acl-collection") -> Collection:
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
        display_title="Test Collection",
        description="Collection description",
        version="1.0",
        location=location,
    )
    return collection


def _create_bundle(collection: Collection, identifier: str = "acl-bundle") -> Bundle:
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
        display_title="Test Bundle",
        description="Bundle description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _store_acl(obj, rules):
    ct = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.update_or_create(
        content_type=ct,
        object_id=obj.pk,
        defaults={
            "ACL_file_bucket": "test-bucket",
            "ACL_file_key": "test/key",
            "permissions_data": rules,
        },
    )[0]


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_detail_allows_public_access(client):
    collection = _create_collection()
    bundle = _create_bundle(collection)
    _store_acl(collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_resources_denies_when_acl_restricts(client):
    collection = _create_collection("restricted-collection")
    bundle = _create_bundle(collection, "restricted-bundle")
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}])

    response = client.get(reverse("explorer:bundle_resources", kwargs={"pk": bundle.pk}))
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_resources_allows_authenticated_agent(client):
    collection = _create_collection("auth-collection")
    bundle = _create_bundle(collection, "auth-bundle")
    _store_acl(bundle, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

    user = get_user_model().objects.create_user(username="viewer", password="pass")
    client.force_login(user)

    response = client.get(reverse("explorer:bundle_resources", kwargs={"pk": bundle.pk}))
    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_resource_access_denied_without_permission(client):
    collection = _create_collection("noaccess-collection")
    bundle = _create_bundle(collection, "noaccess-bundle")
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/other", "mode": ["acl:Read"]}])

    response = client.get(
        reverse(
            "explorer:resource_access",
            kwargs={"bundle_id": bundle.pk, "resource_id": uuid4()},
        )
    )
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_additional_metadata_file_access_allowed_despite_acl(client):
    """Additional metadata files should be public regardless of ACL restrictions."""
    collection = _create_collection("restricted-metadata-collection")
    bundle = _create_bundle(collection, "restricted-metadata-bundle")
    # Restrict access to specific user only
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/other", "mode": ["acl:Read"]}])

    # Create an additional metadata file
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/metadata-file-1",
        file_name="metadata.xml",
        file_description="Test metadata",
        mime_type="application/xml",
    )
    structural_info = bundle.structural_info.first()
    structural_info.additional_metadata_files.add(metadata_file)

    # Anonymous user should be able to access additional metadata file
    # (even though regular resources would be blocked)
    response = client.get(
        reverse(
            "explorer:resource_access",
            kwargs={"bundle_id": bundle.pk, "resource_id": metadata_file.pk},
        )
    )
    # Should not be 403 Forbidden - the file is public
    # It may be 404 if the S3 storage is not configured, but not 403
    assert response.status_code != 403
