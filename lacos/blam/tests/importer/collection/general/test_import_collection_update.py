from unittest.mock import MagicMock, patch

import pytest

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.models.collection.collection_repository import Collection


@pytest.mark.django_db
def test_import_from_xml_update_existing_calls_update():
    collection = Collection.objects.create(identifier="test-collection")
    cmd_data = MagicMock()
    header = MagicMock()
    header.md_self_link = MagicMock(value=collection.identifier)
    cmd_data.header = header
    cmd_data.version = "1.0"

    with patch.object(CollectionImporter, "validate_xml", return_value=cmd_data), \
         patch.object(
             CollectionImporter,
             "_update_existing_collection",
             return_value=collection,
         ) as mock_update:
        result = CollectionImporter.import_from_xml("<xml></xml>", update_existing=True)

    assert result == collection
    mock_update.assert_called_once_with(collection, cmd_data)


@pytest.mark.django_db
def test_import_from_xml_without_update_returns_existing():
    collection = Collection.objects.create(identifier="test-collection-no-update")
    cmd_data = MagicMock()
    header = MagicMock()
    header.md_self_link = MagicMock(value=collection.identifier)
    cmd_data.header = header
    cmd_data.version = "1.0"

    with patch.object(CollectionImporter, "validate_xml", return_value=cmd_data), \
         patch.object(CollectionImporter, "_update_existing_collection") as mock_update:
        result = CollectionImporter.import_from_xml("<xml></xml>", update_existing=False)

    assert result == collection
    mock_update.assert_not_called()
