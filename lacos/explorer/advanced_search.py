"""Advanced per-field search filtering for faceted search views."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.contrib.postgres.search import SearchVector
from django.db.models import Q, QuerySet
from django.http import QueryDict

from lacos.explorer.text_search import build_fts_query


@dataclass(frozen=True)
class AdvancedFieldDefinition:
    """Maps a field key to one or more ORM field paths for FTS."""

    key: str
    label: str
    orm_fields: list[str] = field(default_factory=list)
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
        orm_fields=["general_info__display_title"],
        placeholder="e.g. Interviews about Rock Art",
    ),
    AdvancedFieldDefinition(
        key="description",
        label="Description",
        orm_fields=["general_info__description"],
        placeholder="e.g. video recordings",
    ),
    AdvancedFieldDefinition(
        key="keyword",
        label="Keyword",
        orm_fields=["general_info__keywords__value"],
        placeholder="e.g. language acquisition",
    ),
    AdvancedFieldDefinition(
        key="language",
        label="Language",
        orm_fields=["general_info__object_languages__name"],
        placeholder="e.g. Yuracaré",
    ),
    AdvancedFieldDefinition(
        key="location",
        label="Location / Country",
        orm_fields=[
            "general_info__location__location_name",
            "general_info__location__country_name",
            "general_info__location__country_facet",
            "general_info__location__region_facet",
        ],
        placeholder="e.g. Papua New Guinea",
    ),
    AdvancedFieldDefinition(
        key="creator",
        label="Creator",
        orm_fields=[
            "publication_info__creators__family_name",
            "publication_info__creators__given_name",
        ],
        placeholder="e.g. Hellwig",
    ),
    AdvancedFieldDefinition(
        key="contributor",
        label="Contributor",
        orm_fields=[
            "publication_info__contributors__family_name",
            "publication_info__contributors__given_name",
            "publication_info__contributors__contributor_display_name",
        ],
        placeholder="e.g. Compensis",
    ),
    AdvancedFieldDefinition(
        key="grant_id",
        label="Grant ID",
        orm_fields=["project_infos__funder_infos__grant_identifier"],
        placeholder="e.g. 502013233",
    ),
]


BUNDLE_FIELD_DEFINITIONS: list[AdvancedFieldDefinition] = [
    AdvancedFieldDefinition(
        key="title",
        label="Title",
        orm_fields=["general_info__display_title"],
        placeholder="e.g. Interviews about Rock Art",
    ),
    AdvancedFieldDefinition(
        key="description",
        label="Description",
        orm_fields=["general_info__description"],
        placeholder="e.g. video recordings",
    ),
    AdvancedFieldDefinition(
        key="keyword",
        label="Keyword",
        orm_fields=["general_info__keywords__value"],
        placeholder="e.g. language acquisition",
    ),
    AdvancedFieldDefinition(
        key="language",
        label="Language",
        orm_fields=["general_info__object_languages__name"],
        placeholder="e.g. Yuracaré",
    ),
    AdvancedFieldDefinition(
        key="location",
        label="Location / Country",
        orm_fields=[
            "general_info__location__location_facet",
            "general_info__location__country_facet",
            "general_info__location__region_facet",
        ],
        placeholder="e.g. Papua New Guinea",
    ),
    AdvancedFieldDefinition(
        key="creator",
        label="Creator",
        orm_fields=[
            "publication_info__creators__family_name",
            "publication_info__creators__given_name",
        ],
        placeholder="e.g. Hellwig",
    ),
    AdvancedFieldDefinition(
        key="contributor",
        label="Contributor",
        orm_fields=[
            "publication_info__contributors__family_name",
            "publication_info__contributors__given_name",
            "publication_info__contributors__contributor_name__contributor_family_name",
            "publication_info__contributors__contributor_name__contributor_given_name",
        ],
        placeholder="e.g. Compensis",
    ),
    AdvancedFieldDefinition(
        key="grant_id",
        label="Grant ID",
        orm_fields=["projects__funder_infos__grant_identifier"],
        placeholder="e.g. 502013233",
    ),
    AdvancedFieldDefinition(
        key="collection",
        label="Collection",
        orm_fields=[
            "structural_info__is_member_of_collection__identifier",
            "structural_info__is_member_of_collection__general_info__display_title",
        ],
        placeholder="e.g. Tima Archive Cologne",
    ),
]

# Regex to match row_N_field / row_N_value params
_ROW_PARAM_RE = re.compile(r"^row_(\d+)_(field|value)$")


def parse_search_rows(
    params: QueryDict,
    definitions: list[AdvancedFieldDefinition],
) -> tuple[list[SearchRow], str]:
    """Parse dynamic query builder rows from GET params.

    Expects pairs: row_0_field=title, row_0_value=Senufo, row_1_field=language, ...
    Also reads ``logic`` param (``and`` or ``or``, default ``and``).
    Returns tuple of (list of SearchRow, logic mode).
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

    logic = params.get("logic", "and").lower()
    if logic not in ("and", "or"):
        logic = "and"

    return rows, logic


def apply_search_rows(
    qs: QuerySet,
    rows: list[SearchRow],
    definitions: list[AdvancedFieldDefinition],
    logic: str = "and",
) -> QuerySet:
    """Apply dynamic search rows to the queryset using full-text search.

    When ``logic`` is ``and`` each row narrows the queryset.
    When ``logic`` is ``or`` rows are combined so any match qualifies.
    Within a single row, multiple ORM fields are combined into one SearchVector.
    """
    if not rows:
        return qs

    field_map = {d.key: d.orm_fields for d in definitions}

    row_queries: list[Q] = []
    annotations: dict[str, SearchVector] = {}
    for row in rows:
        fields = field_map.get(row.field_key, [])
        if not fields:
            continue
        fts_query = build_fts_query(row.value)
        if fts_query is None:
            continue
        annotation_name = f"_fts_row_{row.index}"
        vector = SearchVector(*fields, config="simple")
        annotations[annotation_name] = vector
        row_queries.append(Q(**{annotation_name: fts_query}))

    if not row_queries:
        return qs

    qs = qs.annotate(**annotations)

    if logic == "or":
        combined = reduce(or_, row_queries)
        qs = qs.filter(combined)
    else:
        for q in row_queries:
            qs = qs.filter(q)

    return qs.distinct()


def apply_field_scoped_search(
    qs: QuerySet,
    term: str,
    field_keys: list[str],
    definitions: list[AdvancedFieldDefinition],
) -> QuerySet:
    """Filter ``qs`` so ``term`` matches within ANY of the selected fields.

    Builds one SearchVector over the union of the selected definitions' ORM
    field paths and filters with a prefix FTS query. Returns ``qs`` unchanged
    when the term is empty or none of the keys resolve to fields.
    """
    fts_query = build_fts_query(term)
    if fts_query is None:
        return qs
    field_map = {d.key: d.orm_fields for d in definitions}
    orm_fields: list[str] = []
    for key in field_keys:
        orm_fields.extend(field_map.get(key, []))
    if not orm_fields:
        return qs
    vector = SearchVector(*orm_fields, config="simple")
    return (
        qs.annotate(_field_scoped_fts=vector)
        .filter(_field_scoped_fts=fts_query)
        .distinct()
    )
