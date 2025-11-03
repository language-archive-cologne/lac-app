"""Dublin Core mapping rules."""

from __future__ import annotations

from .base import FieldMap

DC_FIELD_MAP = (
    FieldMap(targets=("dc:title",), source="CollectionDisplayTitle"),
    FieldMap(targets=("dc:creator",), source="CollectionCreator"),
    FieldMap(targets=("dc:subject",), source="ObjectLanguageName"),
    FieldMap(targets=("dc:description",), source="CollectionDescription"),
    FieldMap(targets=("dc:date",), source="AvailabilityDate"),
    FieldMap(targets=("dc:type",), constant="Dataset"),
    FieldMap(targets=("dc:format",), constant="audio-visual"),
    FieldMap(targets=("dc:identifier",), source="CollectionID"),
    FieldMap(targets=("dc:language",), source="ObjectLanguageISO639-3Code"),
    FieldMap(targets=("dc:coverage",), source="CollectionGeoLocation"),
    FieldMap(targets=("dc:rights",), source="LicenseIdentifier"),
)
