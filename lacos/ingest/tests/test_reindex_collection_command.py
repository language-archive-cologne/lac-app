import uuid
from unittest.mock import MagicMock, patch

from lacos.ingest.management.commands.reindex_collection import Command


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


@patch("lacos.ingest.management.commands.reindex_collection.close_old_connections")
@patch("lacos.ingest.management.commands.reindex_collection.reindex_bundle_xml")
def test_reindex_bundle_keys_deduplicates_inputs(
    mock_reindex_bundle_xml,
    _mock_close_old_connections,
):
    command = Command()
    discovery_service = MagicMock()
    bundle_id = uuid.uuid4()
    bundle_resources_id = uuid.uuid4()
    mock_reindex_bundle_xml.return_value = (bundle_id, bundle_resources_id)

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
    assert mock_reindex_bundle_xml.call_count == 2
    mock_reindex_bundle_xml.assert_any_call(
        bucket="lacos-production",
        s3_key="col-a/bundle-1/v1/content/bundle-1.xml",
        discovery_service=discovery_service,
    )
    mock_reindex_bundle_xml.assert_any_call(
        bucket="lacos-production",
        s3_key="col-a/bundle-2/v1/content/bundle-2.xml",
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
    command._reindex_collection = MagicMock(side_effect=[uuid.uuid4(), uuid.uuid4()])
    command._reindex_bundle_keys = MagicMock(return_value=[])
    command._update_s3_resource_locations = MagicMock()

    result = command.handle(
        identifier=None,
        prefix="root/",
        bucket="lacos-production",
        all=False,
        update_bundles=True,
        dry_run=False,
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
