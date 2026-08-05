"""Warm shared Explorer facet caches outside user requests."""

from __future__ import annotations

from dataclasses import dataclass

from django.http import QueryDict

from lacos.explorer.facet_querysets import bundle_facet_queryset
from lacos.explorer.facet_querysets import collection_facet_queryset
from lacos.explorer.facets import BUNDLE_FACET_CACHE_KEY
from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.facets import FACET_CACHE_KEY
from lacos.explorer.facets import FacetService


@dataclass(frozen=True)
class FacetWarmResult:
    label: str
    cache_status: str
    duration_ms: float


def warm_explorer_facet_caches(*, refresh: bool = False) -> list[FacetWarmResult]:
    if refresh:
        FacetService.invalidate_cache(FACET_CACHE_KEY, BUNDLE_FACET_CACHE_KEY)

    empty_params = QueryDict()
    configurations = (
        (
            "collection",
            FacetService(),
            collection_facet_queryset(),
            FACET_CACHE_KEY,
        ),
        (
            "bundle",
            FacetService(definitions=BUNDLE_FACET_DEFINITIONS),
            bundle_facet_queryset(),
            BUNDLE_FACET_CACHE_KEY,
        ),
    )

    results = []
    for label, service, queryset, cache_key in configurations:
        result = service.search(empty_params, queryset, cache_key=cache_key)
        results.append(
            FacetWarmResult(
                label=label,
                cache_status=result.cache_status,
                duration_ms=result.facet_duration_ms,
            ),
        )
    return results
