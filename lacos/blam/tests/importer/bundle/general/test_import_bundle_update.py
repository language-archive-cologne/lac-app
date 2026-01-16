import uuid
from unittest.mock import MagicMock, patch

import pytest

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.models.bundle.bundle_repository import Bundle


@pytest.mark.django_db
def test_import_from_xml_update_existing_bundle_calls_update():
    bundle = Bundle.objects.create(identifier="test-bundle")
    cmd_data = MagicMock()
    header = MagicMock()
    header.md_self_link = MagicMock(value=bundle.identifier)
    cmd_data.header = header

    resources_id = uuid.uuid4()

    with patch.object(BundleImporter, "validate_xml", return_value=cmd_data), \
         patch.object(
             BundleImporter,
             "_get_bundle_resources_id",
             return_value=resources_id,
         ), \
         patch.object(
             BundleImporter,
             "_update_existing_bundle",
             return_value=(bundle, resources_id),
         ) as mock_update:
        result = BundleImporter.import_from_xml("<xml></xml>", update_existing=True)

    assert result == (bundle, resources_id)
    mock_update.assert_called_once_with(bundle, cmd_data, bundle.identifier, resources_id)


@pytest.mark.django_db
def test_import_from_xml_without_update_returns_existing_bundle():
    bundle = Bundle.objects.create(identifier="test-bundle-no-update")
    cmd_data = MagicMock()
    header = MagicMock()
    header.md_self_link = MagicMock(value=bundle.identifier)
    cmd_data.header = header

    resources_id = uuid.uuid4()

    with patch.object(BundleImporter, "validate_xml", return_value=cmd_data), \
         patch.object(
             BundleImporter,
             "_get_bundle_resources_id",
             return_value=resources_id,
         ) as mock_get_resources, \
         patch.object(BundleImporter, "_update_existing_bundle") as mock_update:
        result = BundleImporter.import_from_xml("<xml></xml>", update_existing=False)

    assert result == (bundle, resources_id)
    mock_get_resources.assert_called_once_with(bundle)
    mock_update.assert_not_called()
