import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources, BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.ingest.management.commands.reindex_collection import Command
from lacos.ingest.services.reindex_service import (
    BundleReindexResult,
    CollectionReindexResult,
)


def test_group_bundle_keys_by_collection():
    command = Command()

    grouped = command._group_bundle_keys_by_collection(
        [
            "col-a/bundle-1/v1/content/bundle-1.xml",
            "col-a/bundle-2/v1/content/bundle-2.xml",
            "col-b/bundle-3/v1/content/bundle-3.xml",
            "",
        ]
    )

    assert grouped == {
        "col-a": [
            "col-a/bundle-1/v1/content/bundle-1.xml",
            "col-a/bundle-2/v1/content/bundle-2.xml",
        ],
        "col-b": ["col-b/bundle-3/v1/content/bundle-3.xml"],
    }


def test_group_bundle_keys_by_collection_handles_nested_prefixes():
    command = Command()

    grouped = command._group_bundle_keys_by_collection(
        [
            "root/col-a/bundle-1/v1/metadata/bundle-1.xml",
            "root/col-b/bundle-2/v1/metadata/bundle-2.xml",
        ]
    )

    assert grouped == {
        "col-a": ["root/col-a/bundle-1/v1/metadata/bundle-1.xml"],
        "col-b": ["root/col-b/bundle-2/v1/metadata/bundle-2.xml"],
    }


def test_collection_sibling_prefix_handles_nested_collection_xml():
    assert (
        Command._collection_sibling_prefix(
            "root/col-a/col-a/v1/metadata/col-a.xml"
        )
        == "root/col-a/"
    )


@patch("lacos.ingest.management.commands.reindex_collection.close_old_connections")
@patch("lacos.ingest.management.commands.reindex_collection.reindex_bundle_xml_status")
def test_reindex_bundle_keys_deduplicates_inputs(
    mock_reindex_bundle_xml_status,
    _mock_close_old_connections,
):
    command = Command()
    discovery_service = MagicMock()
    bundle_id = uuid.uuid4()
    bundle_resources_id = uuid.uuid4()
    mock_reindex_bundle_xml_status.return_value = BundleReindexResult(
        bundle_id=bundle_id,
        bundle_resources_id=bundle_resources_id,
        skipped=False,
    )

    results = command._reindex_bundle_keys(
        bucket="lacos-production",
        bundle_keys=[
            "col-a/bundle-1/v1/content/bundle-1.xml",
            "col-a/bundle-1/v1/content/bundle-1.xml",
            "col-a/bundle-2/v1/content/bundle-2.xml",
        ],
        discovery_service=discovery_service,
    )

    assert len(results) == 2
    assert mock_reindex_bundle_xml_status.call_count == 2
    mock_reindex_bundle_xml_status.assert_any_call(
        bucket="lacos-production",
        s3_key="col-a/bundle-1/v1/content/bundle-1.xml",
        force=False,
        discovery_service=discovery_service,
    )
    mock_reindex_bundle_xml_status.assert_any_call(
        bucket="lacos-production",
        s3_key="col-a/bundle-2/v1/content/bundle-2.xml",
        force=False,
        discovery_service=discovery_service,
    )


@patch("lacos.ingest.management.commands.reindex_collection.close_old_connections")
@patch("lacos.ingest.management.commands.reindex_collection.reindex_bundle_xml_status")
def test_reindex_bundle_keys_forwards_force(
    mock_reindex_bundle_xml_status,
    _mock_close_old_connections,
):
    command = Command()
    discovery_service = MagicMock()
    bundle_id = uuid.uuid4()
    bundle_resources_id = uuid.uuid4()
    mock_reindex_bundle_xml_status.return_value = BundleReindexResult(
        bundle_id=bundle_id,
        bundle_resources_id=bundle_resources_id,
        skipped=False,
    )

    command._reindex_bundle_keys(
        bucket="lacos-production",
        bundle_keys=["col-a/bundle-1/v1/content/bundle-1.xml"],
        force=True,
        discovery_service=discovery_service,
    )

    mock_reindex_bundle_xml_status.assert_called_once_with(
        bucket="lacos-production",
        s3_key="col-a/bundle-1/v1/content/bundle-1.xml",
        force=True,
        discovery_service=discovery_service,
    )


@patch("lacos.ingest.management.commands.reindex_collection.FileDiscoveryService")
def test_handle_prefix_reindexes_only_associated_bundles(mock_discovery_service_cls):
    discovery_service = MagicMock()
    discovery_service.production_bucket = "lacos-production"
    discovery_service.find_collection_and_bundle_xmls_s3.return_value = {
        "potential_collection_xmls": [
            "col-a/col-a/v1/content/col-a.xml",
            "col-b/col-b/v1/content/col-b.xml",
        ],
        "potential_bundle_xmls": [
            "col-a/bundle-1/v1/content/bundle-1.xml",
            "col-b/bundle-2/v1/content/bundle-2.xml",
            "col-b/bundle-3/v1/content/bundle-3.xml",
        ],
    }
    mock_discovery_service_cls.return_value = discovery_service

    command = Command()
    command._reindex_collection = MagicMock(
        side_effect=[
            CollectionReindexResult(collection_id=uuid.uuid4(), skipped=False),
            CollectionReindexResult(collection_id=uuid.uuid4(), skipped=False),
        ]
    )
    command._reindex_bundle_keys = MagicMock(return_value=[])
    command._update_s3_resource_locations = MagicMock()

    result = command.handle(
        identifier=None,
        prefix="root/",
        bucket="lacos-production",
        all=False,
        update_bundles=True,
        dry_run=False,
        force=False,
    )

    assert result == 0
    assert command._reindex_bundle_keys.call_count == 2

    first_args, _first_kwargs = command._reindex_bundle_keys.call_args_list[0]
    second_args, _second_kwargs = command._reindex_bundle_keys.call_args_list[1]

    assert first_args[1] == ["col-a/bundle-1/v1/content/bundle-1.xml"]
    assert second_args[1] == [
        "col-b/bundle-2/v1/content/bundle-2.xml",
        "col-b/bundle-3/v1/content/bundle-3.xml",
    ]


@patch("lacos.ingest.management.commands.reindex_collection.FileDiscoveryService")
def test_handle_prefix_forwards_force_to_collections_and_bundles(mock_discovery_service_cls):
    discovery_service = MagicMock()
    discovery_service.production_bucket = "lacos-production"
    discovery_service.find_collection_and_bundle_xmls_s3.return_value = {
        "potential_collection_xmls": ["col-a/col-a/v1/content/col-a.xml"],
        "potential_bundle_xmls": ["col-a/bundle-1/v1/content/bundle-1.xml"],
    }
    mock_discovery_service_cls.return_value = discovery_service

    command = Command()
    command._reindex_collection = MagicMock(
        return_value=CollectionReindexResult(collection_id=uuid.uuid4(), skipped=False)
    )
    command._reindex_bundle_keys = MagicMock(return_value=[])
    command._update_s3_resource_locations = MagicMock()

    result = command.handle(
        identifier=None,
        prefix="root/",
        bucket="lacos-production",
        all=False,
        update_bundles=True,
        dry_run=False,
        force=True,
    )

    assert result == 0
    assert command._reindex_collection.call_args.kwargs["force"] is True
    assert command._reindex_bundle_keys.call_args.kwargs["force"] is True


def test_reindex_bundles_for_collection_scopes_discovered_bundles_to_collection():
    collection = SimpleNamespace(
        identifier="col-a",
        import_object_key="root/col-a/col-a/v1/metadata/col-a.xml",
    )
    discovery_service = MagicMock()
    discovery_service.find_collection_and_bundle_xmls_s3.return_value = {
        "potential_collection_xmls": [
            "root/col-a/col-a/v1/metadata/col-a.xml",
        ],
        "potential_bundle_xmls": [
            "root/col-a/bundle-1/v1/metadata/bundle-1.xml",
            "root/col-b/bundle-2/v1/metadata/bundle-2.xml",
        ],
    }

    command = Command()
    command._reindex_bundle_keys = MagicMock(return_value=[])

    result = command._reindex_bundles_for_collection(
        collection,
        bucket="lacos-production",
        dry_run=True,
        force=True,
        discovery_service=discovery_service,
    )

    assert result == []
    discovery_service.find_collection_and_bundle_xmls_s3.assert_called_once_with(
        "lacos-production",
        "root/col-a/",
    )
    command._reindex_bundle_keys.assert_called_once_with(
        "lacos-production",
        ["root/col-a/bundle-1/v1/metadata/bundle-1.xml"],
        dry_run=True,
        force=True,
        discovery_service=discovery_service,
    )


@pytest.mark.django_db
@patch("lacos.ingest.management.commands.reindex_collection.connection.close")
@patch("lacos.ingest.management.commands.reindex_collection.close_old_connections")
@patch("lacos.ingest.management.commands.reindex_collection.FileDiscoveryService")
def test_handle_all_removes_collection_missing_from_storage(
    mock_discovery_service_cls,
    _mock_close_old_connections,
    _mock_connection_close,
):
    collection = Collection.objects.create(
        identifier="hdl:11341/missing-storage-collection",
        import_bucket="lacos-ingest",
        import_object_key=(
            "missing_storage/missing_storage/v1/content/missing_storage.xml"
        ),
    )
    bundle = Bundle.objects.create(
        identifier="hdl:11341/missing-storage-bundle",
        import_object_key=(
            "missing_storage/missing_bundle/v1/content/missing_bundle.xml"
        ),
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )

    discovery_service = MagicMock()
    discovery_service.production_bucket = "lacos-production"
    discovery_service.head_s3_object.return_value = None
    mock_discovery_service_cls.return_value = discovery_service

    command = Command()
    command._reindex_collection = MagicMock()
    command._reindex_bundles_for_collection = MagicMock()
    command._update_s3_resource_locations = MagicMock()

    result = command.handle(
        identifier=None,
        prefix=None,
        bucket=None,
        all=True,
        update_bundles=True,
        dry_run=False,
        force=False,
    )

    assert result == 0
    assert not Collection.objects.filter(id=collection.id).exists()
    assert not Bundle.objects.filter(id=bundle.id).exists()
    command._reindex_collection.assert_not_called()
    command._reindex_bundles_for_collection.assert_not_called()
    command._update_s3_resource_locations.assert_not_called()


@patch("lacos.ingest.management.commands.reindex_collection.ResourceMappingService")
def test_update_s3_resource_locations_uses_none_when_no_bundle_pairs(mock_mapping_service_cls):
    command = Command()
    mapping_service = MagicMock()
    mapping_service.map_collection_hierarchy.return_value = 7
    mock_mapping_service_cls.return_value = mapping_service

    command._update_s3_resource_locations(
        collection_id=uuid.uuid4(),
        bundle_results=[],
        dry_run=False,
    )

    _, kwargs = mapping_service.map_collection_hierarchy.call_args
    assert kwargs["bundle_resources_pairs"] is None


@patch("lacos.ingest.management.commands.reindex_collection.ResourceMappingService")
def test_update_s3_resource_locations_passes_explicit_bundle_pairs(mock_mapping_service_cls):
    command = Command()
    mapping_service = MagicMock()
    mapping_service.map_collection_hierarchy.return_value = 3
    mock_mapping_service_cls.return_value = mapping_service

    bundle_id = uuid.uuid4()
    resources_id = uuid.uuid4()
    command._update_s3_resource_locations(
        collection_id=uuid.uuid4(),
        bundle_results=[(bundle_id, resources_id)],
        dry_run=False,
    )

    _, kwargs = mapping_service.map_collection_hierarchy.call_args
    assert kwargs["bundle_resources_pairs"] == [(bundle_id, resources_id)]


def test_maybe_update_s3_resource_locations_skips_when_unchanged_and_mapped():
    command = Command()
    collection_id = uuid.uuid4()
    command._has_missing_s3_resource_locations = MagicMock(return_value=False)
    command._update_s3_resource_locations = MagicMock()

    command._maybe_update_s3_resource_locations(
        CollectionReindexResult(collection_id=collection_id, skipped=True),
        [
            BundleReindexResult(
                bundle_id=uuid.uuid4(),
                bundle_resources_id=uuid.uuid4(),
                skipped=True,
            )
        ],
    )

    command._has_missing_s3_resource_locations.assert_called_once()
    command._update_s3_resource_locations.assert_not_called()


def test_maybe_update_s3_resource_locations_maps_when_unchanged_but_missing():
    command = Command()
    collection_id = uuid.uuid4()
    bundle_result = BundleReindexResult(
        bundle_id=uuid.uuid4(),
        bundle_resources_id=uuid.uuid4(),
        skipped=True,
    )
    command._has_missing_s3_resource_locations = MagicMock(return_value=True)
    command._update_s3_resource_locations = MagicMock()

    command._maybe_update_s3_resource_locations(
        CollectionReindexResult(collection_id=collection_id, skipped=True),
        [bundle_result],
    )

    command._update_s3_resource_locations.assert_called_once_with(
        collection_id,
        [bundle_result],
        dry_run=False,
        fallback_to_all_bundles=False,
    )


def test_maybe_update_s3_resource_locations_maps_when_collection_changed():
    command = Command()
    collection_id = uuid.uuid4()
    command._has_missing_s3_resource_locations = MagicMock()
    command._update_s3_resource_locations = MagicMock()

    command._maybe_update_s3_resource_locations(
        CollectionReindexResult(collection_id=collection_id, skipped=False),
        [],
        dry_run=True,
    )

    command._has_missing_s3_resource_locations.assert_not_called()
    command._update_s3_resource_locations.assert_called_once_with(
        collection_id,
        [],
        dry_run=True,
        fallback_to_all_bundles=True,
    )


@pytest.mark.django_db
def test_has_missing_s3_resource_locations_detects_existing_collection_mapping():
    from django.contrib.contenttypes.models import ContentType
    from lacos.storage.models.s3_resource_location import S3ResourceLocation

    collection = Collection.objects.create(identifier=f"collection-{uuid.uuid4()}")
    S3ResourceLocation.objects.create(
        content_type=ContentType.objects.get_for_model(Collection),
        object_id=str(collection.id),
        s3_bucket="bucket",
        s3_key="collection/",
    )

    assert Command()._has_missing_s3_resource_locations(collection.id, []) is False


@pytest.mark.django_db
def test_has_missing_s3_resource_locations_detects_missing_resource_mapping():
    from django.contrib.contenttypes.models import ContentType
    from lacos.blam.models.bundle.bundle_structural_info import MediaResource
    from lacos.storage.models.s3_resource_location import S3ResourceLocation

    collection = Collection.objects.create(identifier=f"collection-{uuid.uuid4()}")
    bundle = Bundle.objects.create(identifier=f"bundle-{uuid.uuid4()}")
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    bundle_resources = BundleResources.objects.create(bundle=bundle)
    media_resource = MediaResource.objects.create(
        file_name="audio.wav",
        file_pid=f"https://hdl.handle.net/{uuid.uuid4()}",
        mime_type="audio/wav",
        file_length="10",
    )
    bundle_resources.bundle_media_resources.add(media_resource)

    S3ResourceLocation.objects.create(
        content_type=ContentType.objects.get_for_model(Collection),
        object_id=str(collection.id),
        s3_bucket="bucket",
        s3_key="collection/",
    )
    S3ResourceLocation.objects.create(
        content_type=ContentType.objects.get_for_model(Bundle),
        object_id=str(bundle.id),
        s3_bucket="bucket",
        s3_key="collection/bundle/",
    )

    assert (
        Command()._has_missing_s3_resource_locations(
            collection.id,
            [
                BundleReindexResult(
                    bundle_id=bundle.id,
                    bundle_resources_id=bundle_resources.id,
                    skipped=True,
                )
            ],
        )
        is True
    )
