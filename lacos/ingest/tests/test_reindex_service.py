import uuid
from unittest.mock import MagicMock, patch

import pytest

from lacos.ingest.services.reindex_service import (
    reindex_bundle_xml,
    reindex_collection_xml,
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
    collection.save.assert_called_once_with(
        update_fields=["import_bucket", "import_object_key"]
    )
    assert collection.import_bucket == "test-bucket"
    assert collection.import_object_key == "collection.xml"


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
    bundle.save.assert_called_once_with(
        update_fields=["import_bucket", "import_object_key"]
    )
    assert bundle.import_bucket == "test-bucket"
    assert bundle.import_object_key == "bundle.xml"
