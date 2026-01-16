from __future__ import annotations

from typing import Mapping
from xml.etree import ElementTree as ET

from .dublin_core import DublinCoreSerializer
from .olac import OLACSerializer
from .schema_org import SchemaOrgSerializer
from .blam import BLAMSerializer

SERIALIZERS = {
    DublinCoreSerializer.prefix: DublinCoreSerializer(),
    OLACSerializer.prefix: OLACSerializer(),
    SchemaOrgSerializer.prefix: SchemaOrgSerializer(),
    BLAMSerializer.prefix: BLAMSerializer(),
}


def serialize(prefix: str, record: Mapping[str, object]) -> ET.Element:
    serializer = SERIALIZERS.get(prefix)
    if serializer is None:
        raise ValueError(f"Unsupported metadata prefix: {prefix}")
    return serializer.serialize(record)
