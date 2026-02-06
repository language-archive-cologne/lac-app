from types import SimpleNamespace
from unittest.mock import patch

from lacos.blam.mappers.collection.read.collection_importer import (
    BLAM_VERSION_1_2,
    CollectionImporter,
)
from blam_schemas.collection.blam_collection_repository_v1_2 import Cmd as CmdV12


def _xml_with_component(tag: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CMD xmlns="http://www.clarin.eu/cmd/">
  <Header />
  <Components>
    <{tag} />
  </Components>
</CMD>
"""


def test_detect_version_returns_v12_for_v12_component_tag():
    xml = _xml_with_component("BLAM-collection-repository_v1.2")
    assert CollectionImporter._detect_version(xml) == BLAM_VERSION_1_2


def test_validate_xml_routes_v12_to_v12_parser():
    xml = _xml_with_component("BLAM-collection-repository_v1.2")
    sentinel = SimpleNamespace(version=BLAM_VERSION_1_2)

    with (
        patch.object(CollectionImporter, "_parse_v12", return_value=sentinel) as parse_v12,
        patch.object(CollectionImporter, "_parse_v11") as parse_v11,
        patch.object(CollectionImporter, "_parse_v10") as parse_v10,
    ):
        result = CollectionImporter.validate_xml(xml)

    assert result is sentinel
    parse_v12.assert_called_once()
    parse_v11.assert_not_called()
    parse_v10.assert_not_called()


def test_parse_v12_uses_v12_schema_and_sets_adapter():
    xml = _xml_with_component("BLAM-collection-repository_v1.2")
    mock_repo = object()
    mock_cmd = SimpleNamespace(
        header=SimpleNamespace(md_self_link=None),
        components=SimpleNamespace(blam_collection_repository_v1_2=mock_repo),
    )

    with patch("lacos.blam.mappers.collection.read.collection_importer.XmlParser.from_string", return_value=mock_cmd) as from_string:
        result = CollectionImporter._parse_v12(xml)

    from_string.assert_called_once_with(xml, CmdV12)
    assert result.version == BLAM_VERSION_1_2
    assert result.components.blam_collection_repository_v1_2 is mock_repo
