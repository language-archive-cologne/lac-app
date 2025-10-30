import json

import pytest
from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_sync_service import ACLSyncService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .test_constants import TEST_BUCKET_NAME


@pytest.fixture
def acl_sync_service(mock_s3):
    original_sync = ACLSyncService._instance
    original_mapping = ResourceMappingService._instance
    ACLSyncService._instance = None
    ResourceMappingService._instance = None
    try:
        service = ACLSyncService()
        service.s3_client = mock_s3
        service.production_bucket = TEST_BUCKET_NAME
        service.set_client_and_buckets(service.resource_mapping)
        yield service
    finally:
        ACLSyncService._instance = original_sync
        ResourceMappingService._instance = original_mapping


def _create_collection(identifier: str = "collection-1") -> Collection:
    return Collection.objects.create(identifier=identifier)


def _create_bundle(collection: Collection, identifier: str = "bundle-1") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


@pytest.mark.django_db
def test_sync_collection_creates_permissions(mock_s3, acl_sync_service):
    collection = _create_collection()
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "collections/collection-1"
    collection.save()

    acl_rules = [
        {"agentClass": "foaf:Agent", "mode": ["acl:Read"]},
    ]

    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="collections/collection-1/acl.json",
        Body=json.dumps(acl_rules),
    )

    result = acl_sync_service.sync_collection(collection)

    assert result.found is True
    assert result.updated is True
    assert result.error is None

    ct = ContentType.objects.get_for_model(Collection)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=collection.pk)
    assert permissions.ACL_file_bucket == TEST_BUCKET_NAME
    assert permissions.ACL_file_key.endswith("collections/collection-1/acl.json")
    assert permissions.permissions_data == acl_rules
    assert permissions.last_synced is not None


@pytest.mark.django_db
def test_sync_bundle_handles_missing_acl(mock_s3, acl_sync_service):
    collection = _create_collection()
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "collections/collection-2"
    collection.save()

    bundle = _create_bundle(collection)
    bundle.import_bucket = TEST_BUCKET_NAME
    bundle.import_object_key = "collections/collection-2/bundles/bundle-1"
    bundle.save()

    result = acl_sync_service.sync_bundle(bundle)

    assert result.found is False
    assert result.updated is True  # Record created with bucket/key
    assert result.error is None

    ct = ContentType.objects.get_for_model(Bundle)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=bundle.pk)
    assert permissions.permissions_data is None
    assert permissions.last_synced is None
