"""Advanced per-field search filtering for faceted search views."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.db.models import Q, QuerySet
from django.http import QueryDict


@dataclass(frozen=True)
class AdvancedFieldDefinition:
    """Maps a field key to one or more ORM icontains lookups."""

    key: str
    label: str
    orm_lookups: list[str] = field(default_factory=list)
    placeholder: str = ""


@dataclass
class SearchRow:
    """A single row in the dynamic query builder."""

    field_key: str
    value: str
    index: int = 0


COLLECTION_FIELD_DEFINITIONS: list[AdvancedFieldDefinition] = [
    AdvancedFieldDefinition(
        key="title",
        label="Title",
        orm_lookups=["general_info__display_title__icontains"],
        placeholder="e.g. Senufo",
    ),
    AdvancedFieldDefinition(
        key="description",
        label="Description",
        orm_lookups=["general_info__description__icontains"],
        placeholder="e.g. music recordings",
    ),
    AdvancedFieldDefinition(
        key="keyword",
        label="Keyword",
        orm_lookups=["general_info__keywords__value__icontains"],
        placeholder="e.g. phonetics",
    ),
    AdvancedFieldDefinition(
        key="language",
        label="Language",
        orm_lookups=["general_info__object_languages__name__icontains"],
        placeholder="e.g. Bambara",
    ),
    AdvancedFieldDefinition(
        key="location",
        label="Location / Country",
        orm_lookups=[
            "general_info__location__location_name__icontains",
            "general_info__location__country_name__icontains",
            "general_info__location__country_facet__icontains",
            "general_info__location__region_facet__icontains",
        ],
        placeholder="e.g. Mali",
    ),
    AdvancedFieldDefinition(
        key="creator",
        label="Creator",
        orm_lookups=[
            "publication_info__creators__family_name__icontains",
            "publication_info__creators__given_name__icontains",
        ],
        placeholder="e.g. Vydrin",
    ),
    AdvancedFieldDefinition(
        key="contributor",
        label="Contributor",
        orm_lookups=[
            "publication_info__contributors__family_name__icontains",
            "publication_info__contributors__given_name__icontains",
            "publication_info__contributors__contributor_display_name__icontains",
        ],
        placeholder="e.g. annotator",
    ),
    AdvancedFieldDefinition(
        key="grant_id",
        label="Grant ID",
        orm_lookups=["project_infos__funder_infos__grant_identifier__icontains"],
        placeholder="e.g. DFG-123",
    ),
    AdvancedFieldDefinition(
        key="data_provider",
        label="Data Provider",
        orm_lookups=["publication_info__data_provider__icontains"],
        placeholder="e.g. ELAR",
    ),
]


BUNDLE_FIELD_DEFINITIONS: list[AdvancedFieldDefinition] = [
    AdvancedFieldDefinition(
        key="title",
        label="Title",
        orm_lookups=["general_info__display_title__icontains"],
        placeholder="e.g. Senufo",
    ),
    AdvancedFieldDefinition(
        key="description",
        label="Description",
        orm_lookups=["general_info__description__icontains"],
        placeholder="e.g. music recordings",
    ),
    AdvancedFieldDefinition(
        key="keyword",
        label="Keyword",
        orm_lookups=["general_info__keywords__value__icontains"],
        placeholder="e.g. phonetics",
    ),
    AdvancedFieldDefinition(
        key="language",
        label="Language",
        orm_lookups=["general_info__object_languages__name__icontains"],
        placeholder="e.g. Bambara",
    ),
    AdvancedFieldDefinition(
        key="location",
        label="Location / Country",
        orm_lookups=[
            "general_info__location__location_facet__icontains",
            "general_info__location__country_facet__icontains",
            "general_info__location__region_facet__icontains",
        ],
        placeholder="e.g. Mali",
    ),
    AdvancedFieldDefinition(
        key="creator",
        label="Creator",
        orm_lookups=[
            "publication_info__creators__family_name__icontains",
            "publication_info__creators__given_name__icontains",
        ],
        placeholder="e.g. Vydrin",
    ),
    AdvancedFieldDefinition(
        key="contributor",
        label="Contributor",
        orm_lookups=[
            "publication_info__contributors__family_name__icontains",
            "publication_info__contributors__given_name__icontains",
            "publication_info__contributors__contributor_name__contributor_family_name__icontains",
            "publication_info__contributors__contributor_name__contributor_given_name__icontains",
        ],
        placeholder="e.g. annotator",
    ),
    AdvancedFieldDefinition(
        key="grant_id",
        label="Grant ID",
        orm_lookups=["projects__funder_infos__grant_identifier__icontains"],
        placeholder="e.g. DFG-123",
    ),
    AdvancedFieldDefinition(
        key="collection",
        label="Collection",
        orm_lookups=[
            "structural_info__is_member_of_collection__identifier__icontains",
            "structural_info__is_member_of_collection__general_info__display_title__icontains",
        ],
        placeholder="e.g. Dogon Languages",
    ),
    AdvancedFieldDefinition(
        key="topic",
        label="Topic",
        orm_lookups=["structural_info__bundle_topics__name__icontains"],
        placeholder="e.g. narrative",
    ),
]

# Regex to match row_N_field / row_N_value params
_ROW_PARAM_RE = re.compile(r"^row_(\d+)_(field|value)$")


def parse_search_rows(
    params: QueryDict,
    definitions: list[AdvancedFieldDefinition],
) -> list[SearchRow]:
    """Parse dynamic query builder rows from GET params.

    Expects pairs: row_0_field=title, row_0_value=Senufo, row_1_field=language, ...
    Returns list of SearchRow with valid, non-empty field+value pairs.
    """
    valid_keys = {d.key for d in definitions}
    raw: dict[int, dict[str, str]] = {}

    for param_key in params:
        match = _ROW_PARAM_RE.match(param_key)
        if not match:
            continue
        index = int(match.group(1))
        part = match.group(2)  # "field" or "value"
        raw.setdefault(index, {})[part] = params.get(param_key, "").strip()

    rows: list[SearchRow] = []
    for index in sorted(raw):
        field_key = raw[index].get("field", "")
        value = raw[index].get("value", "")
        if field_key in valid_keys and value:
            rows.append(SearchRow(field_key=field_key, value=value, index=index))
    return rows


def apply_search_rows(
    qs: QuerySet,
    rows: list[SearchRow],
    definitions: list[AdvancedFieldDefinition],
) -> QuerySet:
    """Apply dynamic search rows to the queryset.

    Each row narrows the queryset (AND between rows).
    When a field maps to multiple ORM lookups, they are OR-combined.
    """
    if not rows:
        return qs

    lookup_map = {d.key: d.orm_lookups for d in definitions}

    for row in rows:
        lookups = lookup_map.get(row.field_key, [])
        if not lookups:
            continue
        q = reduce(or_, (Q(**{lookup: row.value}) for lookup in lookups))
        qs = qs.filter(q)

    return qs.distinct()
