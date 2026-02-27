import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from unittest.mock import patch

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_PUBLIC, ACL_LEVEL_RESTRICTED
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_service import ACLService as ACLSyncService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .test_constants import TEST_BUCKET_NAME


@pytest.fixture
def acl_sync_service(mock_s3):
    original_sync = ACLSyncService._instance
    original_mapping = ResourceMappingService._instance
    ACLSyncService._instance = None
    ResourceMappingService._instance = None
    cache.clear()
    try:
        service = ACLSyncService()
        service.s3_client = mock_s3
        service.production_bucket = TEST_BUCKET_NAME
        service.set_client_and_buckets(service.resource_mapping)
        yield service
    finally:
        cache.clear()
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
    """Test ACL sync with legacy path (backward compatibility)."""
    collection = _create_collection()
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "collections/collection-1"
    collection.save()

    acl_rules = [
        {"agentClass": "foaf:Agent", "mode": ["acl:Read"]},
    ]

    # Legacy path (pre-OCFL 1.1)
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="collections/collection-1/acl.json",
        Body=json.dumps(acl_rules),
    )

    result = acl_sync_service.sync_collection(collection)

    assert result.success is True
    assert result.error is None

    ct = ContentType.objects.get_for_model(Collection)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=collection.pk)
    assert permissions.ACL_file_bucket == TEST_BUCKET_NAME
    # ACL key should be the legacy path (fallback)
    assert "acl.json" in permissions.ACL_file_key
    assert permissions.permissions_data == acl_rules
    assert permissions.last_synced is not None
    assert permissions.access_level == ACL_LEVEL_PUBLIC
    assert permissions.read_agents == ["foaf:Agent"]


@pytest.mark.django_db
def test_sync_collection_uses_cached_acl(mock_s3, acl_sync_service):
    """Test ACL caching with OCFL 1.1 extensions path."""
    collection = _create_collection(identifier="collection-cache")
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "collections/collection-cache"
    collection.save()

    acl_rules = [
        {"agentClass": "acl:AuthenticatedAgent", "mode": ["acl:Read"]},
    ]

    # OCFL 1.1 path: extensions/0013-acl/acl.json
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="collections/collection-cache/extensions/0013-acl/acl.json",
        Body=json.dumps(acl_rules),
    )

    with patch.object(acl_sync_service.s3_client, "get_object", wraps=acl_sync_service.s3_client.get_object) as spy_get_object:
        first = acl_sync_service.sync_collection(collection)
        assert first.success is True
        assert spy_get_object.call_count == 1  # Only one call needed for OCFL 1.1 path

    with patch.object(acl_sync_service.s3_client, "get_object", side_effect=AssertionError("Unexpected S3 fetch")):
        second = acl_sync_service.sync_collection(collection)
        assert second.success is True


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

    assert result.success is False  # ACL file missing
    assert result.error is None

    ct = ContentType.objects.get_for_model(Bundle)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=bundle.pk)
    assert permissions.permissions_data is None
    assert permissions.last_synced is None
    assert permissions.access_level == ACL_LEVEL_RESTRICTED
    assert permissions.read_agents is None or permissions.read_agents == []


@pytest.mark.django_db
def test_sync_bundle_preserves_v_prefixed_bundle_segment(mock_s3, acl_sync_service):
    collection = _create_collection(identifier="multicast_veraa")
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "multicast_veraa/v1/content/multicast_veraa.xml"
    collection.save()

    bundle = _create_bundle(collection, identifier="veraa-story")
    bundle.import_bucket = TEST_BUCKET_NAME
    bundle.import_object_key = "multicast_veraa/veraa_story/v1/content/veraa_story.xml"
    bundle.save()

    acl_rules = [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]
    expected_acl_key = "multicast_veraa/veraa_story/acl.json"

    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=expected_acl_key,
        Body=json.dumps(acl_rules),
    )

    result = acl_sync_service.sync_bundle(bundle)
    assert result.success is True
    assert result.key == expected_acl_key

    ct = ContentType.objects.get_for_model(Bundle)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=bundle.pk)
    assert permissions.ACL_file_key == expected_acl_key
    assert permissions.permissions_data == acl_rules


@pytest.mark.django_db
def test_sync_bundle_ocfl11_metadata_path(mock_s3, acl_sync_service):
    """Test ACL loading when import_object_key uses OCFL 1.1 /v1/metadata/ pattern."""
    collection = _create_collection(identifier="qaqet")
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "qaqet/qaqet/v1/metadata/qaqet.xml"
    collection.save()

    bundle = _create_bundle(collection, identifier="bundle-meta")
    bundle.import_bucket = TEST_BUCKET_NAME
    bundle.import_object_key = "qaqet/bundle-meta/v1/metadata/bundle-meta.xml"
    bundle.save()

    acl_rules = [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]

    # OCFL 1.1: ACL in extensions/0013-acl/acl.json
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="qaqet/bundle-meta/extensions/0013-acl/acl.json",
        Body=json.dumps(acl_rules),
    )

    result = acl_sync_service.sync_bundle(bundle)
    assert result.success is True
    assert result.key == "qaqet/bundle-meta/extensions/0013-acl/acl.json"

    ct = ContentType.objects.get_for_model(Bundle)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=bundle.pk)
    assert permissions.permissions_data == acl_rules
    assert permissions.access_level == ACL_LEVEL_PUBLIC


@pytest.mark.django_db
def test_sync_bundle_legacy_xml_path_without_v1(mock_s3, acl_sync_service):
    collection = _create_collection(identifier="multicast_veraa")
    collection.import_bucket = TEST_BUCKET_NAME
    collection.import_object_key = "multicast_veraa/multicast_veraa.xml"
    collection.save()

    bundle = _create_bundle(collection, identifier="veraa-story-legacy")
    bundle.import_bucket = TEST_BUCKET_NAME
    bundle.import_object_key = "multicast_veraa/veraa_story/veraa_story.xml"
    bundle.save()

    acl_rules = [{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}]
    expected_acl_key = "multicast_veraa/veraa_story/acl.json"

    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=expected_acl_key,
        Body=json.dumps(acl_rules),
    )

    result = acl_sync_service.sync_bundle(bundle)
    assert result.success is True
    assert result.key == expected_acl_key

    ct = ContentType.objects.get_for_model(Bundle)
    permissions = ACLPermissions.objects.get(content_type=ct, object_id=bundle.pk)
    assert permissions.ACL_file_key == expected_acl_key
    assert permissions.permissions_data == acl_rules
