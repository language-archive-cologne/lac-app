"""Facet filters and facet value counts in the database."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db.models import CharField
from django.db.models import Count
from django.db.models import Exists
from django.db.models import F
from django.db.models import OuterRef
from django.db.models import QuerySet
from django.db.models import Value
from django.db.models.functions import Cast
from django.db.models.functions import Coalesce

from lacos.explorer.facet_definitions import Facet
from lacos.explorer.facet_definitions import FacetDefinition
from lacos.explorer.facet_definitions import FacetValue
from lacos.explorer.facet_definitions import limit_facet_values
from lacos.explorer.facet_definitions import sort_facet_values


def filter_by_facet(
    qs: QuerySet,
    defn: FacetDefinition,
    values: list[str],
) -> QuerySet:
    """Filter on one facet without multiplying the result rows.

    A join on a multi-valued relation gives one row per matching related
    row. An EXISTS semi-join keeps one row per object, so the caller does
    not need DISTINCT. Annotations on *qs* are not visible inside the
    subquery, so they are filtered directly.
    """
    if defn.filter_lookup.split("__", 1)[0] in qs.query.annotations:
        return qs.filter(**{defn.filter_lookup: values})
    matches = qs.model.objects.filter(
        pk=OuterRef("pk"),
        **{defn.filter_lookup: values},
    )
    return qs.filter(Exists(matches))


def compute_facets(
    definitions: list[FacetDefinition],
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
    cross_qs = _build_cross_querysets(definitions, base_qs, selections)

    # Build one aggregate sub-query per facet, then UNION ALL into one trip.
    rows = _fetch_all_facet_rows(definitions, cross_qs)

    # Group raw rows by facet name.
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["facet_name"]].append(row)

    facets: list[Facet] = []
    for defn in definitions:
        facet_values = _rows_to_facet_values(
            grouped.get(defn.name, []),
            selections.get(defn.name, []),
            label_map=defn.label_map,
        )
        facet_values, truncated = limit_facet_values(
            facet_values,
            complete=defn.filterable,
        )
        sort_facet_values(facet_values, defn)
        facets.append(
            Facet(
                name=defn.name,
                label=defn.label,
                values=facet_values,
                truncated=truncated,
                filterable=defn.filterable,
            ),
        )
    return facets


def _build_cross_querysets(
    definitions: list[FacetDefinition],
    base_qs: QuerySet,
    selections: dict[str, list[str]],
) -> dict[str, QuerySet]:
    """Pre-compute per-facet cross-filter querysets.

    Facets WITHOUT active selections share a single fully-filtered
    queryset.  Only facets WITH a selection get a unique queryset
    (all filters EXCEPT their own).  .distinct() is omitted here;
    Count("pk", distinct=True) handles deduplication in the aggregate.
    """
    if not selections:
        return {defn.name: base_qs for defn in definitions}

    # Fully-filtered qs (all active filters applied)
    fully_filtered = base_qs
    for defn in definitions:
        values = selections.get(defn.name)
        if values:
            fully_filtered = filter_by_facet(fully_filtered, defn, values)

    cross_qs: dict[str, QuerySet] = {}
    for defn in definitions:
        if defn.name not in selections:
            cross_qs[defn.name] = fully_filtered
            continue
        qs = base_qs
        for other_defn in definitions:
            if other_defn.name == defn.name:
                continue
            other_values = selections.get(other_defn.name)
            if other_values:
                qs = filter_by_facet(qs, other_defn, other_values)
        cross_qs[defn.name] = qs
    return cross_qs


def _facet_rows_qs(qs: QuerySet, defn: FacetDefinition) -> QuerySet:
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
    definitions: list[FacetDefinition],
    cross_qs: dict[str, QuerySet],
) -> list[dict[str, Any]]:
    """Fetch all facet counts in one UNION ALL query (single DB round-trip)."""
    union_qs: QuerySet | None = None
    for defn in definitions:
        q = _facet_rows_qs(cross_qs[defn.name], defn)
        union_qs = q if union_qs is None else union_qs.union(q, all=True)
    return list(union_qs) if union_qs is not None else []


def _rows_to_facet_values(
    rows: list[dict[str, Any]],
    selected_list: list[str],
    *,
    label_map: dict[str, str] | None = None,
) -> list[FacetValue]:
    """Convert raw DB rows into an unsorted FacetValue list."""
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
    facet_values.extend(
        FacetValue(value=sel_val, label=sel_val, count=0, selected=True)
        for sel_val in selected_set - seen
    )
    return facet_values
