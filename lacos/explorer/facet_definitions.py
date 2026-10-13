"""Facet value types, facet definitions, and value order rules."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from lacos.explorer.file_types import FILE_TYPE_LABELS

FACET_MAX_VALUES = 30  # Max values shown per facet (selected values always included)

# Value orders for a facet. "fixed" uses the key order of the label map.
FACET_ORDER_COUNT = "count"
FACET_ORDER_LABEL = "label"
FACET_ORDER_NEWEST = "newest"
FACET_ORDER_FIXED = "fixed"


@dataclass(frozen=True)
class FacetValue:
    """A single value within a facet (e.g., one language or one country)."""

    value: str
    label: str
    count: int
    selected: bool = False


@dataclass
class Facet:
    """A facet dimension with its available values."""

    name: str
    label: str
    values: list[FacetValue] = field(default_factory=list)
    truncated: bool = False
    filterable: bool = False

    @property
    def has_selection(self) -> bool:
        return any(v.selected for v in self.values)

    @property
    def selected_values(self) -> list[FacetValue]:
        return [v for v in self.values if v.selected]



@dataclass(frozen=True)
class FacetDefinition:
    """Configuration for a single facet dimension."""

    name: str
    label: str
    value_field: str
    label_field: str
    filter_lookup: str
    label_map: dict[str, str] | None = None
    allowed_values: frozenset[str] | None = None
    order: str = FACET_ORDER_COUNT
    # show_all: no value limit in the database search, with a filter input.
    show_all: bool = False
    # list_all: no value limit in any search backend, with a filter input.
    list_all: bool = False
    integer_values: bool = False

    @property
    def filterable(self) -> bool:
        return self.show_all or self.list_all


FACET_DEFINITIONS: list[FacetDefinition] = [
    FacetDefinition(
        name="keyword",
        label="Collection Keyword",
        value_field="general_info__keywords__value",
        label_field="general_info__keywords__value",
        filter_lookup="general_info__keywords__value__in",
        show_all=True,
    ),
    FacetDefinition(
        name="language",
        label="Language",
        value_field="general_info__object_languages__iso_639_3_code",
        label_field="general_info__object_languages__name",
        filter_lookup="general_info__object_languages__iso_639_3_code__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="file_type",
        label="File format",
        value_field="bundle_file_type_facets__file_type",
        label_field="bundle_file_type_facets__file_type",
        filter_lookup="bundle_file_type_facets__file_type__in",
        label_map=FILE_TYPE_LABELS,
        allowed_values=frozenset(FILE_TYPE_LABELS),
    ),
    FacetDefinition(
        name="year",
        label="Year",
        value_field="publication_info__publication_year",
        label_field="publication_info__publication_year",
        filter_lookup="publication_info__publication_year__in",
        integer_values=True,
        order=FACET_ORDER_NEWEST,
        list_all=True,
    ),
    FacetDefinition(
        name="country",
        label="Country",
        value_field="general_info__location__country_facet",
        label_field="general_info__location__country_facet",
        filter_lookup="general_info__location__country_facet__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="region",
        label="Region",
        value_field="general_info__location__region_facet",
        label_field="general_info__location__region_facet",
        filter_lookup="general_info__location__region_facet__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="access",
        label="Access Level",
        value_field="acl_access_level",
        label_field="acl_access_level",
        filter_lookup="acl_access_level__in",
        order=FACET_ORDER_FIXED,
        label_map={
            "public": "Public",
            "academic": "Academic",
            "restricted": "Restricted",
        },
    ),
    FacetDefinition(
        name="license",
        label="License",
        value_field="administrative_info__licenses__license_name",
        label_field="administrative_info__licenses__license_name",
        filter_lookup="administrative_info__licenses__license_name__in",
        order=FACET_ORDER_LABEL,
    ),
]


BUNDLE_FACET_DEFINITIONS: list[FacetDefinition] = [
    # Ordered from highest to lowest cardinality
    FacetDefinition(
        name="keyword",
        label="Bundle Keyword",
        value_field="general_info__keywords__value",
        label_field="general_info__keywords__value",
        filter_lookup="general_info__keywords__value__in",
        show_all=True,
    ),
    FacetDefinition(
        name="language",
        label="Language",
        value_field="general_info__object_languages__iso_639_3_code",
        label_field="general_info__object_languages__name",
        filter_lookup="general_info__object_languages__iso_639_3_code__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="file_type",
        label="File format",
        value_field="file_type_facets__file_type",
        label_field="file_type_facets__file_type",
        filter_lookup="file_type_facets__file_type__in",
        label_map=FILE_TYPE_LABELS,
        allowed_values=frozenset(FILE_TYPE_LABELS),
    ),
    FacetDefinition(
        name="collection",
        label="Collection",
        value_field="structural_info__is_member_of_collection__identifier",
        label_field="structural_info__is_member_of_collection__general_info__display_title",
        filter_lookup="structural_info__is_member_of_collection__identifier__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="year",
        label="Year",
        value_field="publication_info__publication_year",
        label_field="publication_info__publication_year",
        filter_lookup="publication_info__publication_year__in",
        integer_values=True,
        order=FACET_ORDER_NEWEST,
        list_all=True,
    ),
    FacetDefinition(
        name="country",
        label="Country",
        value_field="general_info__location__country_facet",
        label_field="general_info__location__country_facet",
        filter_lookup="general_info__location__country_facet__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="region",
        label="Region",
        value_field="general_info__location__region_facet",
        label_field="general_info__location__region_facet",
        filter_lookup="general_info__location__region_facet__in",
        order=FACET_ORDER_LABEL,
        list_all=True,
    ),
    FacetDefinition(
        name="access",
        label="Access Level",
        value_field="acl_access_level",
        label_field="acl_access_level",
        filter_lookup="acl_access_level__in",
        order=FACET_ORDER_FIXED,
        label_map={
            "public": "Public",
            "academic": "Academic",
            "restricted": "Restricted",
        },
    ),
    FacetDefinition(
        name="license",
        label="License",
        value_field="administrative_info__licenses__license_name",
        label_field="administrative_info__licenses__license_name",
        filter_lookup="administrative_info__licenses__license_name__in",
        order=FACET_ORDER_LABEL,
    ),
]


def _order_key(value: FacetValue, definition: FacetDefinition) -> tuple:
    if definition.order == FACET_ORDER_NEWEST:
        return (-int(value.value) if value.value.isdigit() else 0,)
    if definition.order == FACET_ORDER_LABEL:
        return (value.label.casefold(), value.value)
    if definition.order == FACET_ORDER_FIXED:
        positions = list(definition.label_map or {})
        if value.value in positions:
            return (positions.index(value.value), "")
        return (len(positions), value.label.casefold())
    return (-value.count, value.label.casefold())


def sort_facet_values(values: list[FacetValue], definition: FacetDefinition) -> None:
    """Sort *values* in place: selected values first, then the facet order."""
    values.sort(key=lambda value: (not value.selected, *_order_key(value, definition)))


def limit_facet_values(
    values: list[FacetValue],
    *,
    complete: bool,
) -> tuple[list[FacetValue], bool]:
    """Keep the selected values and the most frequent others.

    Returns the kept values and True when values were removed.
    """
    if complete or len(values) <= FACET_MAX_VALUES:
        return values, False
    selected = [value for value in values if value.selected]
    others = sorted(
        (value for value in values if not value.selected),
        key=lambda value: (-value.count, value.label.casefold()),
    )
    return selected + others[: FACET_MAX_VALUES - len(selected)], True
