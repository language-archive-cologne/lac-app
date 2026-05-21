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
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionCreator,
    CollectionPublicationInfo,
    CollectionPublicationInfoCreator,
)
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


def _create_resource_rich_bundle(collection: Collection, resource_count: int) -> Bundle:
    bundle = Bundle.objects.create(identifier="bundle-detail-many-resources")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    resources = BundleResources.objects.create(bundle=bundle)

    media_resources = [
        MediaResource(
            file_name=f"media-rich-{index:03d}.wav",
            file_pid=f"https://hdl.handle.net/media-rich-{index:03d}",
            mime_type="audio/wav",
            file_length="12345",
            file_description="Media resource",
        )
        for index in range(resource_count)
    ]
    MediaResource.objects.bulk_create(media_resources)

    created_resources = list(
        MediaResource.objects.filter(file_name__startswith="media-rich-").order_by("file_name")
    )
    resources.bundle_media_resources.add(*created_resources)
    for resource in created_resources:
        _create_s3_location(resource, bucket="test-bucket", key_prefix="media-rich")

    return bundle


def _create_public_collection(identifier: str) -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    collection_ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_PUBLIC,
        permissions_data=[{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}],
    )
    return collection


def _add_publication_creators_with_distinct_xml_export_order(collection: Collection):
    location = CollectionLocation.objects.create(
        geo_location="0, 0",
        location_name="Test Location",
        region_name="Test Region",
        country_name="Test Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        display_title="Totoli",
        description="Totoli test collection",
        version="1.0",
        location=location,
    )
    publication_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    creators = [
        CollectionCreator.objects.create(family_name="Bracks", given_name="Christoph"),
        CollectionCreator.objects.create(family_name="Bardaji i Farre", given_name="Aleix"),
        CollectionCreator.objects.create(family_name="Hasan", given_name="Muhammad"),
        CollectionCreator.objects.create(family_name="Pogi", given_name="Sahlan"),
        CollectionCreator.objects.create(family_name="Himmelmann", given_name="Nikolaus"),
    ]
    for order, creator in zip([4, 3, 2, 1, 0], creators, strict=True):
        CollectionPublicationInfoCreator.objects.create(
            collectionpublicationinfo=publication_info,
            collectioncreator=creator,
            order=order,
        )
    return publication_info, creators


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


@pytest.mark.django_db
def test_collection_detail_creators_use_xml_export_order(client):
    collection = _create_public_collection("hdl:11341/creator-xml-export-order")
    publication_info, creators = _add_publication_creators_with_distinct_xml_export_order(
        collection
    )

    response = client.get(reverse("explorer:collection_detail", kwargs={"pk": collection.pk}))

    assert response.status_code == 200
    expected_creators = list(publication_info.creators.all())
    assert creators
    assert response.context["collection_creators"] == expected_creators
    page = response.content.decode("utf-8")
    assert page.index("Christoph Bracks") < page.index("Nikolaus Himmelmann")
    assert response.context["citation"].startswith(
        "Bracks, Christoph, Aleix Bardaji i Farre, Muhammad Hasan, "
        "Sahlan Pogi & Nikolaus Himmelmann. 2024. Totoli."
    )


@pytest.mark.django_db
def test_bundle_detail_bulk_loads_s3_locations_for_many_resources(client):
    collection = Collection.objects.create(identifier="hdl:11341/bundle-many-resources")
    collection_ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(collection.pk),
        access_level=ACL_LEVEL_PUBLIC,
        permissions_data=[{"agentClass": "foaf:Agent", "mode": ["acl:Read"]}],
    )
    bundle = _create_resource_rich_bundle(collection, 60)

    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("explorer:bundle_detail", kwargs={"pk": bundle.pk}))
        assert response.status_code == 200
        page = response.content.decode("utf-8")

    assert page.count("media-rich-") >= 60
    assert len(captured) <= 55
