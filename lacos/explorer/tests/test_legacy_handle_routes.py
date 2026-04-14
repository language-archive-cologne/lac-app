import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
)
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(identifier="hdl:11341/test-legacy-col"):
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Legacy URL Collection",
        description="Collection for legacy URL tests",
        version="1.0",
        location=location,
    )
    return collection


def _create_bundle(collection, identifier="hdl:11341/test-legacy-bnd"):
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Test Location",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Legacy URL Bundle",
        description="Bundle for legacy URL tests",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _create_resource(bundle, file_pid="hdl:11341/test-legacy-res"):
    resource = MediaResource.objects.create(
        file_name="test.wav",
        file_pid=file_pid,
        mime_type="audio/wav",
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    bundle_resources.bundle_media_resources.add(resource)
    return resource


def _store_acl(obj, rules):
    content_type = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.update_or_create(
        content_type=content_type,
        object_id=obj.pk,
        defaults={
            "ACL_file_bucket": "test-bucket",
            "ACL_file_key": "test/key",
            "permissions_data": rules,
        },
    )[0]


@pytest.mark.django_db
def test_legacy_collection_route_redirects_permanently_and_preserves_query_string(client):
    collection = _create_collection()

    response = client.get(
        f"/collection/{collection.handle_path}/?bundle_sort=access&bundle_order=desc"
    )

    assert response.status_code == 301
    assert response["Location"] == (
        f"/collections/{collection.handle_path}/?bundle_sort=access&bundle_order=desc"
    )


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_legacy_collection_route_redirects_to_acl_protected_canonical_view(client):
    collection = _create_collection("hdl:11341/test-legacy-col-restricted")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(f"/collection/{collection.handle_path}/", follow=True)

    assert response.redirect_chain == [(f"/collections/{collection.handle_path}/", 301)]
    assert response.status_code == 403
    assert "This collection is restricted" in response.content.decode("utf-8")


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_legacy_bundle_route_redirects_to_acl_protected_canonical_view(client):
    collection = _create_collection("hdl:11341/test-legacy-col-restricted")
    bundle = _create_bundle(collection, "hdl:11341/test-legacy-bnd-restricted")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(f"/bundle/{bundle.handle_path}/", follow=True)

    assert response.redirect_chain == [(f"/bundles/{bundle.handle_path}/", 301)]
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_legacy_resource_route_enforces_same_acl_as_canonical_view(client):
    collection = _create_collection("hdl:11341/test-legacy-col-resource")
    bundle = _create_bundle(collection, "hdl:11341/test-legacy-bnd-resource")
    resource = _create_resource(bundle, "hdl:11341/test-legacy-res-resource")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(f"/resource/{resource.file_pid[4:]}/")

    assert response.status_code == 403
