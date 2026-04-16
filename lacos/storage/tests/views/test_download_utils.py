import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources, BundleStructuralInfo, MediaResource
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME
from lacos.storage.views.download_utils import check_resource_authorization
from lacos.users.models import CollectionManagerAssignment


def _request(user=None):
    request = RequestFactory().get("/storage/download/")
    request.user = user or AnonymousUser()
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    return request


def _create_collection(identifier: str = "download-utils-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Download Utils Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Download Utils Collection",
        description="Download Utils Collection Description",
        version="1.0",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection: Collection, identifier: str = "download-utils-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="Download Utils Bundle Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"hdl:test/{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Download Utils Bundle",
        description="Download Utils Bundle Description",
        version="1.0",
        location=location,
    )
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _create_media_resource(bundle: Bundle, file_name: str = "restricted.wav") -> MediaResource:
    resource = MediaResource.objects.create(
        file_name=file_name,
        file_pid=f"hdl:test/{file_name}",
        mime_type="audio/x-wav",
        file_description="Restricted resource",
    )
    BundleResources.objects.create(bundle=bundle).bundle_media_resources.add(resource)
    return resource


def _store_acl(obj, rules):
    content_type = ContentType.objects.get_for_model(obj)
    return ACLPermissions.objects.create(
        content_type=content_type,
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
def test_check_resource_authorization_denies_unresolved_location():
    resource_content_type = ContentType.objects.get_for_model(CollectionAdditionalMetadataFile)
    S3ResourceLocation.objects.create(
        resource_pid="hdl:test/orphan-download",
        s3_bucket="lacos-production",
        s3_key="orphan/file.xml",
        mime_type="application/xml",
        content_type=resource_content_type,
        object_id=str(uuid.uuid4()),
    )

    error = check_resource_authorization(_request(), "lacos-production", "orphan/file.xml")

    assert error == "Access denied"


@pytest.mark.django_db
def test_check_resource_authorization_allows_public_collection_metadata_file():
    collection = _create_collection()
    metadata_file = CollectionAdditionalMetadataFile.objects.create(
        file_pid="hdl:test/public-download-metadata",
        file_name="public.xml",
        file_description="Public metadata",
        mime_type="application/xml",
    )
    collection.structural_info.first().additional_metadata_files.add(metadata_file)
    content_type = ContentType.objects.get_for_model(metadata_file)
    S3ResourceLocation.objects.create(
        resource_pid=metadata_file.file_pid,
        s3_bucket="lacos-production",
        s3_key="collection/public.xml",
        mime_type=metadata_file.mime_type,
        content_type=content_type,
        object_id=str(metadata_file.pk),
    )

    error = check_resource_authorization(_request(), "lacos-production", "collection/public.xml")

    assert error is None


@pytest.mark.django_db
def test_check_resource_authorization_denies_anonymous_for_restricted_bundle_resource():
    collection = _create_collection("download-utils-restricted-collection")
    bundle = _create_bundle(collection, "download-utils-restricted-bundle")
    resource = _create_media_resource(bundle, "restricted-download.wav")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    content_type = ContentType.objects.get_for_model(resource)
    S3ResourceLocation.objects.create(
        resource_pid=resource.file_pid,
        s3_bucket="lacos-production",
        s3_key="restricted/restricted-download.wav",
        mime_type=resource.mime_type,
        content_type=content_type,
        object_id=str(resource.pk),
    )

    error = check_resource_authorization(
        _request(),
        "lacos-production",
        "restricted/restricted-download.wav",
    )

    assert error == "Access denied"


@pytest.mark.django_db
def test_check_resource_authorization_allows_assigned_manager_for_restricted_bundle_resource():
    collection = _create_collection("download-utils-manager-collection")
    bundle = _create_bundle(collection, "download-utils-manager-bundle")
    resource = _create_media_resource(bundle, "manager-download.wav")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    content_type = ContentType.objects.get_for_model(resource)
    S3ResourceLocation.objects.create(
        resource_pid=resource.file_pid,
        s3_bucket="lacos-production",
        s3_key="restricted/manager-download.wav",
        mime_type=resource.mime_type,
        content_type=content_type,
        object_id=str(resource.pk),
    )
    user = get_user_model().objects.create_user(username="download-manager", password="pass")
    _assign_collection_manager(user, collection)

    error = check_resource_authorization(
        _request(user),
        "lacos-production",
        "restricted/manager-download.wav",
    )

    assert error is None


@pytest.mark.django_db
def test_check_resource_authorization_denies_manager_assigned_to_other_collection():
    collection = _create_collection("download-utils-primary-collection")
    other_collection = _create_collection("download-utils-other-collection")
    bundle = _create_bundle(collection, "download-utils-other-manager-bundle")
    resource = _create_media_resource(bundle, "other-manager-download.wav")
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    content_type = ContentType.objects.get_for_model(resource)
    S3ResourceLocation.objects.create(
        resource_pid=resource.file_pid,
        s3_bucket="lacos-production",
        s3_key="restricted/other-manager-download.wav",
        mime_type=resource.mime_type,
        content_type=content_type,
        object_id=str(resource.pk),
    )
    user = get_user_model().objects.create_user(username="other-download-manager", password="pass")
    _assign_collection_manager(user, other_collection)

    error = check_resource_authorization(
        _request(user),
        "lacos-production",
        "restricted/other-manager-download.wav",
    )

    assert error == "Access denied"


@pytest.mark.django_db
def test_check_resource_authorization_bundle_acl_overrides_public_collection():
    collection = _create_collection("download-utils-public-parent-collection")
    bundle = _create_bundle(collection, "download-utils-restricted-child-bundle")
    resource = _create_media_resource(bundle, "bundle-overrides-collection.wav")
    _store_acl(collection, [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}])
    _store_acl(
        bundle,
        [{"agentClass": "foaf:Person", "agent": "urn:test:someone-else", "mode": ["acl:Read"]}],
    )
    content_type = ContentType.objects.get_for_model(resource)
    S3ResourceLocation.objects.create(
        resource_pid=resource.file_pid,
        s3_bucket="lacos-production",
        s3_key="restricted/bundle-overrides-collection.wav",
        mime_type=resource.mime_type,
        content_type=content_type,
        object_id=str(resource.pk),
    )

    error = check_resource_authorization(
        _request(),
        "lacos-production",
        "restricted/bundle-overrides-collection.wav",
    )

    assert error == "Access denied"
