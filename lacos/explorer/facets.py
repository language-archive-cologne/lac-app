"""Faceted search service for collection discovery."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache as django_cache
from django.db.models import CharField, Count, F, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Cast, Coalesce
from django.http import QueryDict

from lacos.blam.models import Bundle, Collection
from lacos.explorer.file_types import FILE_TYPE_LABELS
from lacos.storage.models.acl_permissions import ACLPermissions

logger = logging.getLogger(__name__)

FACET_CACHE_KEY = "explorer:facets:base"
BUNDLE_FACET_CACHE_KEY = "explorer:facets:bundles:base"
FACET_CACHE_TIMEOUT = 60 * 10  # 10 minutes
FACET_MAX_VALUES = 30  # Max values shown per facet (selected values always included)


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


@dataclass
class FacetedSearchResult:
    """Result of a faceted search operation."""

    queryset: QuerySet
    facets: list[Facet]
    active_filters: list[dict[str, str]]
    total_count: int


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
    sort_alphabetically: bool = False
    show_all: bool = False


FACET_DEFINITIONS: list[FacetDefinition] = [
    FacetDefinition(
        name="keyword",
        label="Keyword",
        value_field="general_info__keywords__value",
        label_field="general_info__keywords__value",
        filter_lookup="general_info__keywords__value__in",
        sort_alphabetically=True,
        show_all=True,
    ),
    FacetDefinition(
        name="language",
        label="Language",
        value_field="general_info__object_languages__iso_639_3_code",
        label_field="general_info__object_languages__name",
        filter_lookup="general_info__object_languages__iso_639_3_code__in",
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
    ),
    FacetDefinition(
        name="country",
        label="Country",
        value_field="general_info__location__country_facet",
        label_field="general_info__location__country_facet",
        filter_lookup="general_info__location__country_facet__in",
    ),
    FacetDefinition(
        name="region",
        label="Region",
        value_field="general_info__location__region_facet",
        label_field="general_info__location__region_facet",
        filter_lookup="general_info__location__region_facet__in",
    ),
    FacetDefinition(
        name="access",
        label="Access Level",
        value_field="acl_access_level",
        label_field="acl_access_level",
        filter_lookup="acl_access_level__in",
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
    ),
]


BUNDLE_FACET_DEFINITIONS: list[FacetDefinition] = [
    # Ordered from highest to lowest cardinality
    FacetDefinition(
        name="keyword",
        label="Keyword",
        value_field="general_info__keywords__value",
        label_field="general_info__keywords__value",
        filter_lookup="general_info__keywords__value__in",
        sort_alphabetically=True,
        show_all=True,
    ),
    FacetDefinition(
        name="language",
        label="Language",
        value_field="general_info__object_languages__iso_639_3_code",
        label_field="general_info__object_languages__name",
        filter_lookup="general_info__object_languages__iso_639_3_code__in",
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
    ),
    FacetDefinition(
        name="year",
        label="Year",
        value_field="publication_info__publication_year",
        label_field="publication_info__publication_year",
        filter_lookup="publication_info__publication_year__in",
    ),
    FacetDefinition(
        name="country",
        label="Country",
        value_field="general_info__location__country_facet",
        label_field="general_info__location__country_facet",
        filter_lookup="general_info__location__country_facet__in",
    ),
    FacetDefinition(
        name="region",
        label="Region",
        value_field="general_info__location__region_facet",
        label_field="general_info__location__region_facet",
        filter_lookup="general_info__location__region_facet__in",
    ),
    FacetDefinition(
        name="access",
        label="Access Level",
        value_field="acl_access_level",
        label_field="acl_access_level",
        filter_lookup="acl_access_level__in",
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
    ),
]


class FacetService:
    """Parses query params, applies filters, and computes cross-facet counts."""

    def __init__(self, definitions: list[FacetDefinition] | None = None):
        self.definitions = definitions or FACET_DEFINITIONS

    def search(
        self,
        params: QueryDict,
        base_qs: QuerySet,
        *,
        cache_key: str | None = None,
    ) -> FacetedSearchResult:
        """Run faceted search: filter the queryset and compute facet counts.

        When *cache_key* is provided and no facet selections are active,
        facet counts are served from / written to the Django cache.

        NOTE: total_count is left as -1 here; the view should use the
        paginator's count to avoid a duplicate COUNT query.
        """
        base_qs = self._ensure_required_annotations(base_qs)
        selections = self._parse_selections(params)
        filtered_qs = self._apply_filters(base_qs, selections)

        # Use cached facets when the query is the unfiltered base case.
        facets: list[Facet] | None = None
        if not selections and cache_key:
            facets = django_cache.get(cache_key)
            if facets is not None:
                logger.debug("Facet cache hit: %s", cache_key)

        if facets is None:
            facets = self._compute_facets(base_qs, selections)
            if not selections and cache_key:
                django_cache.set(cache_key, facets, FACET_CACHE_TIMEOUT)
                logger.debug("Facet cache set: %s", cache_key)

        active_filters = self._build_active_filters(selections, facets)

        return FacetedSearchResult(
            queryset=filtered_qs,
            facets=facets,
            active_filters=active_filters,
            total_count=-1,
        )

    def _ensure_required_annotations(self, qs: QuerySet) -> QuerySet:
        needs_acl_access_level = any(
            "acl_access_level" in (defn.value_field, defn.label_field, defn.filter_lookup)
            for defn in self.definitions
        )
        if not needs_acl_access_level:
            return qs

        if "acl_access_level" in qs.query.annotations:
            return qs

        if qs.model not in {Collection, Bundle}:
            return qs

        content_type = ContentType.objects.get_for_model(qs.model)
        return qs.annotate(
            acl_access_level=Subquery(
                ACLPermissions.objects.filter(
                    content_type=content_type,
                    object_id=Cast(OuterRef("pk"), output_field=CharField()),
                ).values("access_level")[:1]
            )
        )

    def _parse_selections(self, params: QueryDict) -> dict[str, list[str]]:
        """Extract selected facet values from query params, deduplicated."""
        selections: dict[str, list[str]] = {}
        for defn in self.definitions:
            raw_values = params.getlist(defn.name)
            cleaned = list(dict.fromkeys(v.strip() for v in raw_values if v.strip()))
            if defn.allowed_values is not None:
                cleaned = [v for v in cleaned if v in defn.allowed_values]
            if cleaned:
                selections[defn.name] = cleaned
        return selections

    def _apply_filters(
        self, qs: QuerySet, selections: dict[str, list[str]]
    ) -> QuerySet:
        """Apply all active facet filters (AND between facets, OR within)."""
        for defn in self.definitions:
            values = selections.get(defn.name)
            if values:
                qs = qs.filter(**{defn.filter_lookup: values})
        return qs.distinct()

    def _compute_facets(
        self,
        base_qs: QuerySet,
        selections: dict[str, list[str]],
    ) -> list[Facet]:
        """Compute facet values with cross-facet counting.

        For each facet, counts are computed against the base queryset filtered
        by all OTHER facets (not the current one). This gives users accurate
        counts showing what they'll get if they toggle a value.

        All facet counts are fetched in a single UNION ALL query (one DB
        round-trip instead of one per facet).  Cross-filter querysets omit
        .distinct() because Count("pk", distinct=True) already deduplicates.
        """
        active_names = set(selections.keys())
        cross_qs_cache = self._build_cross_qs_cache(base_qs, selections, active_names)

        # Build one aggregate sub-query per facet, then UNION ALL into one trip.
        rows = self._fetch_all_facet_rows(cross_qs_cache)

        # Group raw rows by facet name.
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["facet_name"]].append(row)

        facets: list[Facet] = []
        for defn in self.definitions:
            facet_values = self._rows_to_facet_values(
                grouped.get(defn.name, []),
                selections.get(defn.name, []),
                label_map=defn.label_map,
                sort_alphabetically=defn.sort_alphabetically,
            )
            truncated = not defn.show_all and len(facet_values) > FACET_MAX_VALUES
            if truncated:
                # Keep selected values + top N by count
                selected = [fv for fv in facet_values if fv.selected]
                unselected = [fv for fv in facet_values if not fv.selected]
                facet_values = selected + unselected[: FACET_MAX_VALUES - len(selected)]
            facets.append(
                Facet(
                    name=defn.name,
                    label=defn.label,
                    values=facet_values,
                    truncated=truncated,
                    filterable=defn.show_all,
                )
            )
        return facets

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_cross_qs_cache(
        self,
        base_qs: QuerySet,
        selections: dict[str, list[str]],
        active_names: set[str],
    ) -> dict[str, QuerySet]:
        """Pre-compute per-facet cross-filter querysets.

        Facets WITHOUT active selections share a single fully-filtered
        queryset.  Only facets WITH a selection get a unique queryset
        (all filters EXCEPT their own).  .distinct() is omitted here;
        Count("pk", distinct=True) handles deduplication in the aggregate.
        """
        cache: dict[str, QuerySet] = {}

        if not active_names:
            for defn in self.definitions:
                cache[defn.name] = base_qs
            return cache

        # Fully-filtered qs (all active filters applied)
        fully_filtered = base_qs
        for defn in self.definitions:
            values = selections.get(defn.name)
            if values:
                fully_filtered = fully_filtered.filter(
                    **{defn.filter_lookup: values}
                )

        for defn in self.definitions:
            if defn.name not in active_names:
                cache[defn.name] = fully_filtered
            else:
                qs = base_qs
                for other_defn in self.definitions:
                    if other_defn.name == defn.name:
                        continue
                    other_values = selections.get(other_defn.name)
                    if other_values:
                        qs = qs.filter(
                            **{other_defn.filter_lookup: other_values}
                        )
                cache[defn.name] = qs
        return cache

    def _facet_rows_qs(self, qs: QuerySet, defn: FacetDefinition) -> QuerySet:
        """Build a single facet's aggregate queryset.

        Casts value/label to text so all UNION branches share the same types.
        """
        if defn.allowed_values is not None:
            qs = qs.filter(**{f"{defn.value_field}__in": defn.allowed_values})
        return (
            qs.annotate(
                facet_name=Value(defn.name, output_field=CharField()),
                facet_value=Cast(F(defn.value_field), output_field=CharField()),
                facet_label=Cast(
                    Coalesce(F(defn.label_field), F(defn.value_field)),
                    output_field=CharField(),
                ),
            )
            .exclude(facet_value__isnull=True)
            .exclude(facet_value="")
            .values("facet_name", "facet_value", "facet_label")
            .annotate(facet_count=Count("pk", distinct=True))
            .values("facet_name", "facet_value", "facet_label", "facet_count")
        )

    def _fetch_all_facet_rows(
        self, cross_qs_cache: dict[str, QuerySet]
    ) -> list[dict[str, Any]]:
        """Fetch all facet counts in one UNION ALL query (single DB round-trip)."""
        union_qs: QuerySet | None = None
        for defn in self.definitions:
            q = self._facet_rows_qs(cross_qs_cache[defn.name], defn)
            union_qs = q if union_qs is None else union_qs.union(q, all=True)
        return list(union_qs) if union_qs is not None else []

    def _rows_to_facet_values(
        self,
        rows: list[dict[str, Any]],
        selected_list: list[str],
        *,
        label_map: dict[str, str] | None = None,
        sort_alphabetically: bool = False,
    ) -> list[FacetValue]:
        """Convert raw DB rows into sorted FacetValue list."""
        counts: dict[str, dict[str, Any]] = {}
        for row in rows:
            val = row["facet_value"]
            label = (label_map or {}).get(val) or row["facet_label"] or val
            count = row["facet_count"]
            if val not in counts:
                counts[val] = {"label": label, "count": count}
            else:
                counts[val]["count"] += count

        selected_set = set(selected_list)
        facet_values = [
            FacetValue(
                value=v,
                label=info["label"],
                count=info["count"],
                selected=v in selected_set,
            )
            for v, info in counts.items()
        ]

        # Preserve selected values even if count dropped to 0
        seen = {fv.value for fv in facet_values}
        for sel_val in selected_set:
            if sel_val not in seen:
                facet_values.append(
                    FacetValue(value=sel_val, label=sel_val, count=0, selected=True)
                )

        if sort_alphabetically:
            facet_values.sort(key=lambda fv: (not fv.selected, fv.label.lower()))
        else:
            facet_values.sort(key=lambda fv: (not fv.selected, -fv.count, fv.label))
        return facet_values

    @staticmethod
    def invalidate_cache() -> None:
        """Clear cached base facet counts for collections and bundles."""
        django_cache.delete(FACET_CACHE_KEY)
        django_cache.delete(BUNDLE_FACET_CACHE_KEY)

    def _build_active_filters(
        self,
        selections: dict[str, list[str]],
        facets: list[Facet],
    ) -> list[dict[str, str]]:
        """Build list of active filter chips for display."""
        # Build a lookup: (facet_name, value) -> label
        label_map: dict[tuple[str, str], str] = {}
        for facet in facets:
            for fv in facet.values:
                label_map[(facet.name, fv.value)] = fv.label

        defn_labels = {d.name: d.label for d in self.definitions}

        active: list[dict[str, str]] = []
        for facet_name, values in selections.items():
            for val in values:
                active.append(
                    {
                        "facet_name": facet_name,
                        "facet_label": defn_labels.get(facet_name, facet_name),
                        "value": val,
                        "label": label_map.get((facet_name, val), val),
                    }
                )
        return active
