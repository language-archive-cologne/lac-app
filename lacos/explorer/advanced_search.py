"""Advanced per-field search filtering for faceted search views."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.postgres.search import SearchVector
from django.db.models import Q, QuerySet

from lacos.explorer.text_search import build_fts_query


@dataclass(frozen=True)
class AdvancedFieldDefinition:
    """Maps a field key to one or more ORM field paths for FTS."""

    key: str
    label: str
    orm_fields: list[str] = field(default_factory=list)
    placeholder: str = ""


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

def apply_field_scoped_search(
    qs: QuerySet,
    term: str,
    field_keys: list[str],
    definitions: list[AdvancedFieldDefinition],
) -> QuerySet:
    """Filter ``qs`` so ``term`` matches within ANY of the selected fields.

    Builds one SearchVector over the union of the selected definitions' ORM
    field paths and filters with a prefix FTS query. Returns ``qs`` unchanged
    when the term is empty or none of the keys resolve to fields. Returns an
    empty queryset when a non-empty term has no searchable tokens.
    """
    if not term.strip():
        return qs
    fts_query = build_fts_query(term)
    if fts_query is None:
        return qs.none()
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
