"""OLAC serializer."""

from __future__ import annotations

from typing import Mapping

from .base import BaseSerializer
from ..mappings.olac import OLAC_FIELD_MAP

OLAC_NS = "http://www.language-archives.org/OLAC/1.1/"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"


class OLACSerializer(BaseSerializer):
    prefix = "olac"
    root_tag = "olac:olac"
    namespace_map = {
        "olac": OLAC_NS,
        "dc": DC_NS,
        "dcterms": DCTERMS_NS,
    }
    field_map = OLAC_FIELD_MAP

    def serialize(self, record: Mapping[str, object]):
        element = super().serialize(record)
        element.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        element.set(
            "xsi:schemaLocation",
            f"{OLAC_NS} http://www.language-archives.org/OLAC/1.1/olac.xsd",
        )
        return element


def serialize(record: Mapping[str, object]):
    return OLACSerializer().serialize(record)
