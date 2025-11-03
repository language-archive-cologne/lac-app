"""Dublin Core serializer."""

from __future__ import annotations

from typing import Mapping

from .base import BaseSerializer
from ..mappings.dc import DC_FIELD_MAP

OAI_DC_NS = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DC_NS = "http://purl.org/dc/elements/1.1/"


class DublinCoreSerializer(BaseSerializer):
    prefix = "oai_dc"
    root_tag = "oai_dc:dc"
    namespace_map = {
        "oai_dc": OAI_DC_NS,
        "dc": DC_NS,
    }
    field_map = DC_FIELD_MAP

    def serialize(self, record: Mapping[str, object]):
        element = super().serialize(record)
        element.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        element.set(
            "xsi:schemaLocation",
            f"{OAI_DC_NS} http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
        )
        return element


def serialize(record: Mapping[str, object]):
    return DublinCoreSerializer().serialize(record)
