import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
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
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.users.models import CollectionManagerAssignment


def _create_collection(identifier: str = "policy-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Policy Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Policy Collection",
        description="Policy Collection Description",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection: Collection, identifier: str = "policy-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Policy Bundle Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Policy Bundle",
        description="Policy Bundle Description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _create_media_resource(bundle: Bundle, file_name: str = "recording.wav") -> MediaResource:
    resource = MediaResource.objects.create(
        file_name=file_name,
        file_pid=f"hdl:test/{file_name}",
        mime_type="audio/x-wav",
        file_description="Restricted audio",
    )
    BundleResources.objects.create(bundle=bundle).bundle_media_resources.add(resource)
    return resource


def _store_acl(obj, rules):
    ct = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.create(
        content_type=ct,
        object_id=obj.pk,
        ACL_file_bucket="test-bucket",
        ACL_file_key="test/key",
        permissions_data=rules,
    )


def _assign_collection_manager(user, collection: Collection) -> None:
    group = Group.objects.get_or_create(name=COLLECTION_MANAGER_GROUP_NAME)[0]
    user.groups.add(group)
    CollectionManagerAssignment.objects.create(user=user, collection=collection)


@pytest.mark.django_db
def test_metadata_policy_keeps_collection_bundle_and_resource_metadata_public():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    resource = _create_media_resource(bundle)
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    policy = ExposurePolicyService()

    assert policy.can_view_metadata(AnonymousUser(), collection) is True
    assert policy.can_view_metadata(AnonymousUser(), bundle) is True
    assert policy.can_view_metadata(AnonymousUser(), resource) is True
    assert policy.can_list_in_search(AnonymousUser(), bundle) is True
    assert policy.can_appear_in_sitemap(AnonymousUser(), collection) is True
    assert policy.can_harvest_via_oai(AnonymousUser(), bundle) is True


@pytest.mark.django_db
def test_binary_policy_denies_anonymous_for_restricted_bundle_resource():
    collection = _create_collection("restricted-binary-collection")
    bundle = _create_bundle(collection, "restricted-binary-bundle")
    resource = _create_media_resource(bundle, "restricted.wav")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    policy = ExposurePolicyService()

    assert policy.can_download_binary(AnonymousUser(), bundle) is False
    assert policy.can_download_binary(AnonymousUser(), resource) is False


@pytest.mark.django_db
def test_binary_policy_allows_assigned_collection_manager_for_restricted_resource():
    collection = _create_collection("manager-binary-collection")
    bundle = _create_bundle(collection, "manager-binary-bundle")
    resource = _create_media_resource(bundle, "manager.wav")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    user = get_user_model().objects.create_user(username="policy-manager", password="pass")
    _assign_collection_manager(user, collection)

    policy = ExposurePolicyService()

    assert policy.can_download_binary(user, resource) is True


@pytest.mark.django_db
def test_binary_policy_allows_public_additional_metadata_file():
    collection = _create_collection("metadata-binary-collection")
    bundle = _create_bundle(collection, "metadata-binary-bundle")
    metadata_file = BundleAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/public-metadata",
        file_name="public.xml",
        file_description="Public bundle metadata",
        mime_type="application/xml",
    )
    bundle.structural_info.first().additional_metadata_files.add(metadata_file)
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )

    policy = ExposurePolicyService()

    assert policy.can_download_binary(AnonymousUser(), metadata_file) is True


@pytest.mark.django_db
def test_binary_policy_denies_unresolved_s3_location():
    collection = _create_collection("location-policy-collection")
    resource_content_type = ContentType.objects.get_for_model(MediaResource)
    location = S3ResourceLocation.objects.create(
        resource_pid="hdl:test/unresolved",
        s3_bucket="lacos-production",
        s3_key="missing/object.wav",
        mime_type="audio/x-wav",
        content_type=resource_content_type,
        object_id=str(uuid.uuid4()),
    )

    policy = ExposurePolicyService()

    assert policy.can_download_binary(AnonymousUser(), location) is False
