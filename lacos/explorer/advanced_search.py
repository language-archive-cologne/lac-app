"""Advanced per-field search filtering for faceted search views."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from django.db.models import Q, QuerySet
from django.http import QueryDict


@dataclass(frozen=True)
class AdvancedFieldDefinition:
    """Maps a GET param to one or more ORM icontains lookups."""

    param_name: str
    label: str
    orm_lookups: list[str] = field(default_factory=list)
    placeholder: str = ""


COLLECTION_FIELD_DEFINITIONS: list[AdvancedFieldDefinition] = [
    AdvancedFieldDefinition(
        param_name="field_title",
        label="Title",
        orm_lookups=["general_info__display_title__icontains"],
        placeholder="e.g. Senufo",
    ),
    AdvancedFieldDefinition(
        param_name="field_description",
        label="Description",
        orm_lookups=["general_info__description__icontains"],
        placeholder="e.g. music recordings",
    ),
    AdvancedFieldDefinition(
        param_name="field_keyword",
        label="Keyword",
        orm_lookups=["general_info__keywords__value__icontains"],
        placeholder="e.g. phonetics",
    ),
    AdvancedFieldDefinition(
        param_name="field_language",
        label="Language",
        orm_lookups=["general_info__object_languages__name__icontains"],
        placeholder="e.g. Bambara",
    ),
    AdvancedFieldDefinition(
        param_name="field_location",
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
        param_name="field_creator",
        label="Creator",
        orm_lookups=[
            "publication_info__creators__family_name__icontains",
            "publication_info__creators__given_name__icontains",
        ],
        placeholder="e.g. Vydrin",
    ),
    AdvancedFieldDefinition(
        param_name="field_contributor",
        label="Contributor",
        orm_lookups=[
            "publication_info__contributors__family_name__icontains",
            "publication_info__contributors__given_name__icontains",
            "publication_info__contributors__contributor_display_name__icontains",
        ],
        placeholder="e.g. annotator",
    ),
    AdvancedFieldDefinition(
        param_name="field_grant_id",
        label="Grant ID",
        orm_lookups=["project_infos__funder_infos__grant_identifier__icontains"],
        placeholder="e.g. DFG-123",
    ),
    AdvancedFieldDefinition(
        param_name="field_data_provider",
        label="Data Provider",
        orm_lookups=["publication_info__data_provider__icontains"],
        placeholder="e.g. ELAR",
    ),
]


BUNDLE_FIELD_DEFINITIONS: list[AdvancedFieldDefinition] = [
    AdvancedFieldDefinition(
        param_name="field_title",
        label="Title",
        orm_lookups=["general_info__display_title__icontains"],
        placeholder="e.g. Senufo",
    ),
    AdvancedFieldDefinition(
        param_name="field_description",
        label="Description",
        orm_lookups=["general_info__description__icontains"],
        placeholder="e.g. music recordings",
    ),
    AdvancedFieldDefinition(
        param_name="field_keyword",
        label="Keyword",
        orm_lookups=["general_info__keywords__value__icontains"],
        placeholder="e.g. phonetics",
    ),
    AdvancedFieldDefinition(
        param_name="field_language",
        label="Language",
        orm_lookups=["general_info__object_languages__name__icontains"],
        placeholder="e.g. Bambara",
    ),
    AdvancedFieldDefinition(
        param_name="field_location",
        label="Location / Country",
        orm_lookups=[
            "general_info__location__location_facet__icontains",
            "general_info__location__country_facet__icontains",
            "general_info__location__region_facet__icontains",
        ],
        placeholder="e.g. Mali",
    ),
    AdvancedFieldDefinition(
        param_name="field_creator",
        label="Creator",
        orm_lookups=[
            "publication_info__creators__family_name__icontains",
            "publication_info__creators__given_name__icontains",
        ],
        placeholder="e.g. Vydrin",
    ),
    AdvancedFieldDefinition(
        param_name="field_contributor",
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
        param_name="field_grant_id",
        label="Grant ID",
        orm_lookups=["projects__funder_infos__grant_identifier__icontains"],
        placeholder="e.g. DFG-123",
    ),
    AdvancedFieldDefinition(
        param_name="field_collection",
        label="Collection",
        orm_lookups=[
            "structural_info__is_member_of_collection__identifier__icontains",
            "structural_info__is_member_of_collection__general_info__display_title__icontains",
        ],
        placeholder="e.g. Dogon Languages",
    ),
    AdvancedFieldDefinition(
        param_name="field_topic",
        label="Topic",
        orm_lookups=["structural_info__bundle_topics__name__icontains"],
        placeholder="e.g. narrative",
    ),
]


def parse_advanced_params(
    params: QueryDict,
    definitions: list[AdvancedFieldDefinition],
) -> dict[str, str]:
    """Extract advanced field values from query params.

    Returns a dict mapping param_name -> stripped value for non-empty fields.
    """
    known = {d.param_name for d in definitions}
    result: dict[str, str] = {}
    for key in params:
        if key not in known:
            continue
        value = params.get(key, "").strip()
        if value:
            result[key] = value
    return result


def apply_advanced_filters(
    qs: QuerySet,
    params: QueryDict,
    definitions: list[AdvancedFieldDefinition],
) -> QuerySet:
    """Apply per-field icontains filters to the queryset.

    Each non-empty field_* param narrows the queryset (AND between fields).
    When a field maps to multiple ORM lookups, they are OR-combined.
    """
    parsed = parse_advanced_params(params, definitions)
    if not parsed:
        return qs

    lookup_map = {d.param_name: d.orm_lookups for d in definitions}

    for param_name, value in parsed.items():
        lookups = lookup_map.get(param_name, [])
        if not lookups:
            continue
        q = reduce(or_, (Q(**{lookup: value}) for lookup in lookups))
        qs = qs.filter(q)

    return qs.distinct()
