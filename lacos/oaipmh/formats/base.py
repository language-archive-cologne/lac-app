"""Base classes for metadata serialization."""

from __future__ import annotations

from typing import Iterable, Mapping
from xml.etree import ElementTree as ET

from ..mappings.base import FieldMap


class BaseSerializer:
    prefix: str
    root_tag: str
    namespace_map: Mapping[str, str]
    field_map: Iterable[FieldMap]

    def __init__(self) -> None:
        for prefix, uri in self.namespace_map.items():
            ET.register_namespace(prefix, uri)

    def serialize(self, record: Mapping[str, object]) -> ET.Element:
        root = self._create_element(self.root_tag)
        for field in self.field_map:
            for target, value in field.resolve(record):
                self._append_value(root, target, value)
        return root

    def _create_element(self, tag: str) -> ET.Element:
        prefix, local = self._split_tag(tag)
        namespace = self.namespace_map[prefix]
        return ET.Element(f"{{{namespace}}}{local}")

    def _append_value(self, parent: ET.Element, tag: str, value: object) -> None:
        prefix, local = self._split_tag(tag)
        namespace = self.namespace_map[prefix]
        child = ET.SubElement(parent, f"{{{namespace}}}{local}")
        child.text = str(value)

    @staticmethod
    def _split_tag(tag: str) -> tuple[str, str]:
        if ":" not in tag:
            raise ValueError(f"Expected prefix-qualified tag, got '{tag}'")
        return tuple(tag.split(":", 1))  # type: ignore[return-value]
