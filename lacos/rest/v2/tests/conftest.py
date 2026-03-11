import pytest
from rest_framework.test import APIClient

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def collection(db):
    return Collection.objects.create(identifier="hdl:11341/0000-0000-0000-TEST")


@pytest.fixture
def collection_with_metadata(db):
    from lacos.blam.models.collection.collection_general_info import (
        CollectionGeneralInfo,
        CollectionLocation,
    )
    from lacos.blam.models.collection.collection_administrative_info import (
        CollectionAdministrativeInfo,
    )

    col = Collection.objects.create(identifier="hdl:11341/0000-0000-0000-COL1")

    location = CollectionLocation.objects.create()
    CollectionGeneralInfo.objects.create(
        collection=col,
        id_value="hdl:11341/0000-0000-0000-COL1",
        id_type="HANDLE",
        display_title="Test Collection",
        description="A test collection for API v2",
        version="1.0",
        location=location,
    )
    CollectionAdministrativeInfo.objects.create(
        collection=col,
        access_level="public",
        availability_date="2025-01-01",
    )
    return col


@pytest.fixture
def bundle_with_metadata(collection_with_metadata):
    from lacos.blam.models.bundle.bundle_general_info import (
        BundleGeneralInfo,
        BundleLocation,
    )
    from lacos.blam.models.bundle.bundle_administrative_info import (
        BundleAdministrativeInfo,
    )
    from lacos.blam.models.bundle.bundle_structural_info import (
        BundleStructuralInfo,
    )

    bundle = Bundle.objects.create(identifier="hdl:11341/0000-0000-0000-BDL1")

    location = BundleLocation.objects.create()
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value="hdl:11341/0000-0000-0000-BDL1",
        id_type="HANDLE",
        display_title="Test Bundle",
        description="A test bundle for API v2",
        version="1.0",
        location=location,
    )
    BundleAdministrativeInfo.objects.create(
        bundle=bundle,
        access_level="public",
        availability_date="2025-01-01",
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection_with_metadata,
    )
    return bundle


@pytest.fixture
def media_resource(bundle_with_metadata):
    from lacos.blam.models.bundle.bundle_structural_info import (
        BundleResources,
        MediaResource,
    )

    resource = MediaResource.objects.create(
        file_name="recording.wav",
        file_pid="hdl:11341/0000-0000-0000-RES1",
        mime_type="audio/x-wav",
        file_length="48000",
    )
    br = BundleResources.objects.create(bundle=bundle_with_metadata)
    br.bundle_media_resources.add(resource)
    return resource


@pytest.fixture
def media_resource_with_s3(media_resource):
    from django.contrib.contenttypes.models import ContentType

    from lacos.storage.models.s3_resource_location import S3ResourceLocation

    ct = ContentType.objects.get_for_model(media_resource)
    S3ResourceLocation.objects.create(
        resource_pid=media_resource.file_pid,
        s3_bucket="lacos-production",
        s3_key="test-collection/test-bundle/recording.wav",
        mime_type=media_resource.mime_type,
        size_bytes=8000000,
        content_type=ct,
        object_id=media_resource.id,
    )
    return media_resource
