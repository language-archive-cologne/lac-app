import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError

from lacos.blam.models.collection.collection_repository import Collection
from lacos.ingest.services.reindex_service import (
    reindex_bundle_xml,
    reindex_bundle_xml_status,
    reindex_collection_xml,
    reindex_collection_xml_status,
)


@pytest.mark.django_db
def test_reindex_collection_xml_updates_import_fields():
    discovery_service = MagicMock()
    discovery_service.read_s3_object.return_value = b"<xml></xml>"

    collection = MagicMock()
    collection.id = uuid.uuid4()
    collection.import_bucket = None
    collection.import_object_key = None
    collection.save = MagicMock()

    with patch(
        "lacos.ingest.services.reindex_service.CollectionImporter.import_from_xml",
        return_value=collection,
    ) as mock_import:
        result = reindex_collection_xml(
            bucket="test-bucket",
            s3_key="collection.xml",
            discovery_service=discovery_service,
        )

    assert result == collection.id
    mock_import.assert_called_once_with("<xml></xml>", update_existing=True)
    # save called for import fields and then for ETag
    save_calls = collection.save.call_args_list
    assert save_calls[0].kwargs == {"update_fields": ["import_bucket", "import_object_key"]}
    assert collection.import_bucket == "test-bucket"
    assert collection.import_object_key == "collection.xml"


@pytest.mark.django_db
def test_reindex_collection_xml_status_reports_etag_skip():
    discovery_service = MagicMock()
    discovery_service.head_s3_object.return_value = {"ETag": "same-etag"}
    collection = Collection.objects.create(
        identifier=f"collection-{uuid.uuid4()}",
        import_object_key="collection.xml",
        import_etag="same-etag",
    )

    result = reindex_collection_xml_status(
        bucket="test-bucket",
        s3_key="collection.xml",
        discovery_service=discovery_service,
    )

    assert result.collection_id == collection.id
    assert result.skipped is True
    discovery_service.read_s3_object.assert_not_called()


@pytest.mark.django_db
def test_reindex_bundle_xml_updates_import_fields():
    discovery_service = MagicMock()
    discovery_service.read_s3_object.return_value = b"<xml></xml>"

    bundle = MagicMock()
    bundle.id = uuid.uuid4()
    bundle.import_bucket = None
    bundle.import_object_key = None
    bundle.save = MagicMock()
    resources_id = uuid.uuid4()

    with patch(
        "lacos.ingest.services.reindex_service.BundleImporter.import_from_xml",
        return_value=(bundle, resources_id),
    ) as mock_import:
        result = reindex_bundle_xml(
            bucket="test-bucket",
            s3_key="bundle.xml",
            discovery_service=discovery_service,
        )

    assert result == (bundle.id, resources_id)
    mock_import.assert_called_once_with("<xml></xml>", update_existing=True)
    # save called for import fields and then for ETag
    save_calls = bundle.save.call_args_list
    assert save_calls[0].kwargs == {"update_fields": ["import_bucket", "import_object_key"]}
    assert bundle.import_bucket == "test-bucket"
    assert bundle.import_object_key == "bundle.xml"


@pytest.mark.django_db
def test_reindex_bundle_xml_status_reports_changed_import():
    discovery_service = MagicMock()
    discovery_service.read_s3_object.return_value = b"<xml></xml>"
    discovery_service.head_s3_object.return_value = {"ETag": "new-etag"}

    bundle = MagicMock()
    bundle.id = uuid.uuid4()
    bundle.import_bucket = "test-bucket"
    bundle.import_object_key = "bundle.xml"
    bundle.save = MagicMock()
    resources_id = uuid.uuid4()

    with patch(
        "lacos.ingest.services.reindex_service.BundleImporter.import_from_xml",
        return_value=(bundle, resources_id),
    ):
        result = reindex_bundle_xml_status(
            bucket="test-bucket",
            s3_key="bundle.xml",
            discovery_service=discovery_service,
        )

    assert result.bundle_id == bundle.id
    assert result.bundle_resources_id == resources_id
    assert result.skipped is False


@pytest.mark.django_db
def test_reindex_collection_xml_returns_none_on_import_error():
    discovery_service = MagicMock()
    discovery_service.read_s3_object.return_value = b"<xml></xml>"

    with patch(
        "lacos.ingest.services.reindex_service.CollectionImporter.import_from_xml",
        side_effect=ValidationError("Invalid BLAM collection XML"),
    ):
        result = reindex_collection_xml(
            bucket="test-bucket",
            s3_key="bad-collection.xml",
            discovery_service=discovery_service,
        )

    assert result is None


@pytest.mark.django_db
def test_reindex_bundle_xml_returns_none_on_import_error():
    discovery_service = MagicMock()
    discovery_service.read_s3_object.return_value = b"<xml></xml>"

    with patch(
        "lacos.ingest.services.reindex_service.BundleImporter.import_from_xml",
        side_effect=ValidationError("Invalid BLAM bundle XML"),
    ):
        result = reindex_bundle_xml(
            bucket="test-bucket",
            s3_key="bad-bundle.xml",
            discovery_service=discovery_service,
        )

    assert result is None
