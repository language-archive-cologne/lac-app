"""Schema.org Dataset serializer."""

from __future__ import annotations

from typing import Mapping

from .base import BaseSerializer
from ..mappings.schema_org import SCHEMA_ORG_FIELD_MAP

SCHEMA_NS = "https://schema.org/"


class SchemaOrgSerializer(BaseSerializer):
    prefix = "schema_org"
    root_tag = "schema:Dataset"
    namespace_map = {
        "schema": SCHEMA_NS,
    }
    field_map = SCHEMA_ORG_FIELD_MAP

    def serialize(self, record: Mapping[str, object]):
        element = super().serialize(record)
        return element


def serialize(record: Mapping[str, object]):
    return SchemaOrgSerializer().serialize(record)
