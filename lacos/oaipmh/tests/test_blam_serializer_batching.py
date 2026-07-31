"""Tests for batched BLAM (CMDI) serialization.

A ListRecords page serializes up to page-size records; the BLAM serializer
must fetch them in one batch with a query count independent of how many
records the page holds, without changing the exported XML.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
    MediaResource,
    WrittenResource,
    WrittenResourceAnnotation,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.oaipmh.formats.blam import BLAMSerializer


def _make_collection(identifier: str = "hdl:test/blam-col") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Collection Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="BLAM Test Collection",
        description="Collection for BLAM batching tests",
        version="1.0",
        location=location,
    )
    return collection


def _make_bundle(i: int, collection: Collection) -> Bundle:
    bundle = Bundle.objects.create(identifier=f"hdl:test/blam-bun-{i:02d}")
    location = BundleLocation.objects.create(
        location_name=f"Site {i}",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=bundle.identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=f"BLAM Test Bundle {i}",
        description="Bundle for BLAM batching tests",
        version="1.0",
        location=location,
    )
    media = MediaResource.objects.create(
        file_name=f"media-{i}.wav",
        file_pid=f"https://hdl.example/media-{i}",
        mime_type="audio/wav",
        file_length="1234",
    )
    written = WrittenResource.objects.create(
        file_name=f"text-{i}.txt",
        file_pid=f"https://hdl.example/text-{i}",
        mime_type="text/plain",
    )
    WrittenResourceAnnotation.objects.create(
        written_resource=written,
        is_annotation_of=f"https://hdl.example/media-{i}",
    )
    resources = BundleResources.objects.create(bundle=bundle)
    resources.bundle_media_resources.add(media)
    resources.bundle_written_resources.add(written)
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _records_for(bundles: list[Bundle], collection: Collection) -> list[dict]:
    records = [
        {"CollectionID": bundle.identifier, "BundleID": bundle.identifier}
        for bundle in bundles
    ]
    records.append({"CollectionID": collection.identifier})
    return records


@pytest.mark.django_db
def test_serialize_many_matches_individual_serialization():
    collection = _make_collection()
    bundles = [_make_bundle(i, collection) for i in range(3)]
    records = _records_for(bundles, collection)

    serializer = BLAMSerializer()
    batched = serializer.serialize_many(records)
    individual = [serializer.serialize(record) for record in records]
    assert batched == individual


@pytest.mark.django_db
def test_serialize_many_query_count_is_independent_of_page_size():
    collection = _make_collection()
    bundles = [_make_bundle(i, collection) for i in range(6)]

    serializer = BLAMSerializer()

    with CaptureQueriesContext(connection) as small:
        serializer.serialize_many(_records_for(bundles[:2], collection))
    with CaptureQueriesContext(connection) as large:
        serializer.serialize_many(_records_for(bundles, collection))

    assert len(large.captured_queries) == len(small.captured_queries)


@pytest.mark.django_db
def test_serialized_bundle_contains_resources_annotations_and_membership():
    collection = _make_collection()
    bundle = _make_bundle(1, collection)

    xml = BLAMSerializer().serialize_many(
        [{"CollectionID": bundle.identifier, "BundleID": bundle.identifier}]
    )[0]

    assert "media-1.wav" in xml
    assert "https://hdl.example/media-1" in xml
    assert "text-1.txt" in xml
    assert "<IsAnnotationOf>https://hdl.example/media-1</IsAnnotationOf>" in xml
    assert collection.identifier.removeprefix("hdl:") in xml


@pytest.mark.django_db
def test_serialize_many_unknown_identifiers_yield_empty_cmd():
    xml = BLAMSerializer().serialize_many(
        [{"CollectionID": "hdl:test/missing", "BundleID": "hdl:test/missing"},
         {"CollectionID": "hdl:test/also-missing"}]
    )
    assert all("<CMD" in item for item in xml)
    assert all("MediaResource" not in item for item in xml)
