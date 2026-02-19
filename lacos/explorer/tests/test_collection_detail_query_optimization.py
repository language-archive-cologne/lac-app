import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.constants import ACL_LEVEL_PUBLIC
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.models.s3_resource_location import S3ResourceLocation


def _create_s3_location(resource, *, bucket: str, key_prefix: str):
    content_type = ContentType.objects.get_for_model(resource)
    S3ResourceLocation.objects.create(
        content_type=content_type,
        object_id=str(resource.pk),
        s3_bucket=bucket,
        s3_key=f"{key_prefix}/{resource.pk}",
        size_bytes=1024,
        mime_type=getattr(resource, "mime_type", None),
    )


def _create_bundle_graph(collection: Collection, index: int) -> Bundle:
    bundle = Bundle.objects.create(identifier=f"bundle-detail-query-opt-{index}")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)

    resources = BundleResources.objects.create(bundle=bundle)
    media = MediaResource.objects.create(
        file_name=f"media-{index}.wav",
        file_pid=f"https://hdl.handle.net/media-{index}",
        mime_type="audio/wav",
        file_length="12345",
        file_description="Media resource",
    )
    written = WrittenResource.objects.create(
        file_name=f"written-{index}.eaf",
        file_pid=f"https://hdl.handle.net/written-{index}",
        mime_type="text/x-eaf+xml",
        file_description="Written resource",
    )
    other = OtherResource.objects.create(
        file_name=f"other-{index}.pdf",
        file_pid=f"https://hdl.handle.net/other-{index}",
        mime_type="application/pdf",
        file_description="Other resource",
    )

    resources.bundle_media_resources.add(media)
    resources.bundle_written_resources.add(written)
    resources.bundle_other_resources.add(other)

    _create_s3_location(media, bucket="test-bucket", key_prefix="media")
    _create_s3_location(written, bucket="test-bucket", key_prefix="written")
    _create_s3_location(other, bucket="test-bucket", key_prefix="other")

    return bundle


@pytest.mark.django_db
def test_collection_detail_query_budget_with_resource_rich_bundles(client):
    collection = Collection.objects.create(identifier="hdl:11341/detail-query-budget")

    collection_ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_PUBLIC,
        permissions_data=[{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}],
    )

    for index in range(1, 6):
        _create_bundle_graph(collection, index)

    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))
        assert response.status_code == 200
        _ = response.content

    assert len(captured) <= 40
