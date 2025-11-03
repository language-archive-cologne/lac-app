"""Schema.org Dataset mapping rules."""

from __future__ import annotations

from .base import FieldMap

SCHEMA_ORG_FIELD_MAP = (
    FieldMap(targets=("schema:name",), source="CollectionDisplayTitle"),
    FieldMap(targets=("schema:creator",), source="CollectionCreator"),
    FieldMap(targets=("schema:about",), source="ObjectLanguageName"),
    FieldMap(targets=("schema:description",), source="CollectionDescription"),
    FieldMap(targets=("schema:datePublished",), source="AvailabilityDate"),
    FieldMap(targets=("schema:type",), constant="Dataset"),
    FieldMap(targets=("schema:encodingFormat",), constant="audio-visual"),
    FieldMap(targets=("schema:identifier", "schema:url"), source="CollectionID"),
    FieldMap(targets=("schema:inLanguage",), source="ObjectLanguageISO639-3Code"),
    FieldMap(targets=("schema:locationCreated",), source="CollectionGeoLocation"),
    FieldMap(targets=("schema:license",), source="LicenseIdentifier"),
    FieldMap(targets=("schema:copyrightHolder",), source="RightsHolder"),
    FieldMap(targets=("schema:version",), source="CollectionVersion"),
)
