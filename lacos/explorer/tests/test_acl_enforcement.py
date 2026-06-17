import pytest
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
)
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.storage.constants import WAC_AUTHENTICATED_AGENT
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.users.models import CollectionManagerAssignment


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
    CollectionStructuralInfo.objects.create(collection=collection)
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


def _assign_collection_manager(user, *collections: Collection) -> None:
    group = Group.objects.get_or_create(name=COLLECTION_MANAGER_GROUP_NAME)[0]
    user.groups.add(group)
    for collection in collections:
        CollectionManagerAssignment.objects.create(user=user, collection=collection)


def _add_bundle_media_resource(bundle: Bundle, file_name: str = "restricted-audio.wav") -> MediaResource:
    resource = MediaResource.objects.create(
        file_name=file_name,
        file_pid=f"hdl:test/{file_name}",
        mime_type="audio/x-wav",
        file_description="Restricted resource",
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    bundle_resources.bundle_media_resources.add(resource)
    return resource


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
def test_collection_detail_shows_metadata_when_acl_restricts(client):
    collection = _create_collection("restricted-collection-detail")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    assert "Collection description" in response.content.decode("utf-8")


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_detail_obeys_metadata_exposure_policy(client, monkeypatch):
    collection = _create_collection("policy-denied-collection-detail")

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_view_metadata",
        lambda self, user, obj: False,
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_metadata_jsonld_allows_when_acl_restricts(client):
    collection = _create_collection("restricted-collection-jsonld")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("explorer:collection_jsonld_by_handle", kwargs={"handle": collection.handle_path})
    )

    assert response.status_code == 200
    assert "application/ld+json" in response["Content-Type"]


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_metadata_xml_allows_when_acl_restricts(client):
    collection = _create_collection("restricted-collection-xml")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("explorer:collection_xml_by_handle", kwargs={"handle": collection.handle_path})
    )

    assert response.status_code == 200
    assert "application/xml" in response["Content-Type"]


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_detail_shows_metadata_when_acl_restricts(client):
    collection = _create_collection("restricted-collection")
    bundle = _create_bundle(collection, "restricted-bundle")
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}])

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))
    assert response.status_code == 200
    assert "Bundle description" in response.content.decode("utf-8")


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_metadata_jsonld_allows_when_acl_restricts(client):
    collection = _create_collection("restricted-bundle-jsonld-collection")
    bundle = _create_bundle(collection, "restricted-bundle-jsonld")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("explorer:bundle_jsonld_by_handle", kwargs={"handle": bundle.handle_path})
    )

    assert response.status_code == 200
    assert "application/ld+json" in response["Content-Type"]


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_metadata_jsonld_obeys_metadata_exposure_policy(client, monkeypatch):
    collection = _create_collection("policy-denied-bundle-jsonld-collection")
    bundle = _create_bundle(collection, "policy-denied-bundle-jsonld")

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_view_metadata",
        lambda self, user, obj: False,
    )

    response = client.get(
        reverse("explorer:bundle_jsonld_by_handle", kwargs={"handle": bundle.handle_path})
    )

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_metadata_xml_allows_when_acl_restricts(client):
    collection = _create_collection("restricted-bundle-xml-collection")
    bundle = _create_bundle(collection, "restricted-bundle-xml")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    response = client.get(
        reverse("explorer:bundle_xml_by_handle", kwargs={"handle": bundle.handle_path})
    )

    assert response.status_code == 200
    assert "application/xml" in response["Content-Type"]


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_detail_hides_restricted_content_but_keeps_metadata_files(client):
    collection = _create_collection("restricted-bundle-files")
    bundle = _create_bundle(collection, "restricted-bundle-files")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )
    _add_bundle_media_resource(bundle, "secret.wav")

    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/public-metadata",
        file_name="public-metadata.xml",
        file_description="Public metadata",
        mime_type="application/xml",
    )
    bundle.structural_info.first().additional_metadata_files.add(metadata_file)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    html = response.content.decode("utf-8")
    assert response.status_code == 200
    assert "You do not have permission to download files from this bundle." in html
    assert "public-metadata.xml" in html
    assert "secret.wav" not in html
    assert f"/resource/{metadata_file.file_pid[4:]}/?action=view" in html


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_detail_allows_assigned_collection_manager(client):
    collection = _create_collection("manager-collection-detail")
    _store_acl(
        collection,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    user = get_user_model().objects.create_user(username="manager-collection-viewer", password="pass")
    _assign_collection_manager(user, collection)
    client.force_login(user)

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_detail_allows_assigned_collection_manager(client):
    collection = _create_collection("manager-bundle-collection")
    bundle = _create_bundle(collection, "manager-bundle-detail")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "http://example.org/users/allowed", "mode": ["acl:Read"]}],
    )

    user = get_user_model().objects.create_user(username="manager-bundle-viewer", password="pass")
    _assign_collection_manager(user, collection)
    client.force_login(user)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))

    assert response.status_code == 200


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_detail_allows_authenticated_agent(client):
    collection = _create_collection("auth-collection")
    bundle = _create_bundle(collection, "auth-bundle")
    _store_acl(bundle, [{"agentClass": WAC_AUTHENTICATED_AGENT, "mode": ["acl:Read"]}])

    user = get_user_model().objects.create_user(username="viewer", password="pass")
    client.force_login(user)

    response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))
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
def test_resource_access_allows_assigned_collection_manager(client):
    collection = _create_collection("manager-resource-collection")
    bundle = _create_bundle(collection, "manager-resource-bundle")
    _store_acl(bundle, [{"agentClass": "foaf:Person", "agent": "http://example.org/users/other", "mode": ["acl:Read"]}])

    user = get_user_model().objects.create_user(username="manager-resource-viewer", password="pass")
    _assign_collection_manager(user, collection)
    client.force_login(user)

    response = client.get(
        reverse(
            "explorer:resource_access",
            kwargs={"bundle_id": bundle.pk, "resource_id": uuid4()},
        )
    )

    assert response.status_code == 404


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


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_resource_route_rejects_resource_from_other_bundle(client):
    collection = _create_collection("bundle-membership-collection")
    bundle = _create_bundle(collection, "bundle-membership-bundle")
    other_bundle = _create_bundle(collection, "bundle-membership-other")
    _store_acl(bundle, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
    _store_acl(other_bundle, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])

    foreign_resource = _add_bundle_media_resource(other_bundle, "foreign.wav")

    response = client.get(
        reverse(
            "explorer:resource_access_by_handle",
            kwargs={"handle": bundle.handle_path, "resource_pid": foreign_resource.file_pid},
        )
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_bundle_resource_route_rejects_metadata_from_other_bundle(client):
    collection = _create_collection("bundle-metadata-membership-collection")
    bundle = _create_bundle(collection, "bundle-metadata-membership-bundle")
    other_bundle = _create_bundle(collection, "bundle-metadata-membership-other")
    _store_acl(bundle, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
    _store_acl(other_bundle, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])

    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/foreign-bundle-metadata",
        file_name="foreign.xml",
        file_description="Foreign bundle metadata",
        mime_type="application/xml",
    )
    other_bundle.structural_info.first().additional_metadata_files.add(metadata_file)

    response = client.get(
        reverse(
            "explorer:resource_access_by_handle",
            kwargs={"handle": bundle.handle_path, "resource_pid": metadata_file.file_pid},
        )
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_metadata_route_rejects_metadata_from_other_collection(client):
    collection = _create_collection("collection-membership-collection")
    other_collection = _create_collection("collection-membership-other")
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/other-collection-metadata",
        file_name="other.xml",
        file_description="Other collection metadata",
        mime_type="application/xml",
    )
    other_collection.structural_info.first().additional_metadata_files.add(metadata_file)

    response = client.get(
        reverse(
            "explorer:collection_resource_by_handle",
            kwargs={"handle": collection.handle_path, "resource_id": metadata_file.file_pid[4:]},
        )
    )

    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(ACL_ENFORCEMENT_ENABLED=True)
def test_collection_metadata_route_obeys_binary_exposure_policy(client, monkeypatch):
    collection = _create_collection("policy-denied-collection-metadata")
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/policy-denied-collection-metadata",
        file_name="policy.xml",
        file_description="Policy denied metadata",
        mime_type="application/xml",
    )
    collection.structural_info.first().additional_metadata_files.add(metadata_file)

    monkeypatch.setattr(
        ExposurePolicyService,
        "can_download_binary",
        lambda self, user, obj: False,
    )

    response = client.get(
        reverse(
            "explorer:collection_resource_by_handle",
            kwargs={"handle": collection.handle_path, "resource_id": metadata_file.file_pid[4:]},
        )
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_flat_resource_handle_resolves_collection_metadata_file(client, monkeypatch):
    """A flat /resource/<handle>/ URL resolves a collection-level metadata file.

    Regression for #158: collection additional metadata file handles previously
    returned 404 because ResourceByHandleView only searched bundle-level models.
    """
    collection = _create_collection("flat-handle-collection-metadata")
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/flat-handle-collection-metadata",
        file_name="meta.xml",
        file_description="Collection metadata",
        mime_type="application/xml",
    )
    collection.structural_info.first().additional_metadata_files.add(metadata_file)

    # Binary exposure is denied after the file is resolved but before any storage
    # access, so a 403 (not 404) proves the flat handle resolved to the file.
    monkeypatch.setattr(
        ExposurePolicyService,
        "can_download_binary",
        lambda self, user, obj: False,
    )

    response = client.get(
        reverse("resource_by_handle", kwargs={"handle_id": metadata_file.file_pid[4:]})
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_flat_resource_handle_unknown_returns_404(client):
    response = client.get(
        reverse("resource_by_handle", kwargs={"handle_id": "test/does-not-exist"})
    )

    assert response.status_code == 404
