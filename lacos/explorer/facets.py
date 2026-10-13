"""Faceted search service for collection discovery."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, replace
from time import monotonic, perf_counter, sleep

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache as django_cache
from django.db.models import CharField, OuterRef, QuerySet, Subquery
from django.db.models.functions import Cast
from django.http import QueryDict

from lacos.blam.models import Bundle, Collection
from lacos.explorer.facet_counts import compute_facets, filter_by_facet
from lacos.explorer.facet_definitions import (
    FACET_DEFINITIONS,
    Facet,
    FacetDefinition,
    FacetValue,
    sort_facet_values,
)
from lacos.storage.models.acl_permissions import ACLPermissions

logger = logging.getLogger(__name__)

FACET_CACHE_KEY = "explorer:facets:base"
BUNDLE_FACET_CACHE_KEY = "explorer:facets:bundles:base"
COLLECTION_FACET_VERSION_KEY = "explorer:facets:collections:version"
BUNDLE_FACET_VERSION_KEY = "explorer:facets:bundles:version"
FACET_CACHE_TIMEOUT = 60 * 60 * 6  # 6 hours; writes explicitly invalidate it.
FACET_MAX_SELECTED_VALUES = 4
FACET_MAX_TOTAL_SELECTED_VALUES = 8
FACET_CACHE_LOCK_TIMEOUT = 30
FACET_CACHE_LOCK_WAIT_SECONDS = 2.0

FACET_VERSION_KEYS = {
    FACET_CACHE_KEY: COLLECTION_FACET_VERSION_KEY,
    BUNDLE_FACET_CACHE_KEY: BUNDLE_FACET_VERSION_KEY,
}


class FacetSelectionLimitError(ValueError):
    """Raised when a request exceeds the supported facet-selection budget."""


class FacetCacheBusyError(RuntimeError):
    """Raised when another request is already rebuilding the same facet cache."""


@dataclass
class FacetedSearchResult:
    """Result of a faceted search operation."""

    queryset: QuerySet
    facets: list[Facet]
    active_filters: list[dict[str, str]]
    cache_status: str = "disabled"
    facet_duration_ms: float = 0.0

    @property
    def server_timing(self) -> str:
        return (
            f'facets;dur={self.facet_duration_ms:.1f};desc="{self.cache_status}"'
        )


class FacetService:
    """Parses query params, applies filters, and computes cross-facet counts."""

    def __init__(self, definitions: list[FacetDefinition] | None = None):
        self.definitions = definitions or FACET_DEFINITIONS

    @staticmethod
    def get_cached_facets(cache_key: str) -> list[Facet]:
        """Read prewarmed facets without rebuilding them from the database."""
        try:
            full_key = FacetService._build_cache_key(cache_key)
            facets = django_cache.get(full_key)
        except Exception:  # noqa: BLE001 -- cache failure must keep the shell DB-free.
            logger.exception(
                "Unable to read prewarmed facet shell",
                extra={"cache_key": cache_key},
            )
            return []
        return facets if isinstance(facets, list) else []

    def search(
        self,
        params: QueryDict,
        base_qs: QuerySet,
        *,
        cache_key: str | None = None,
        cross_filter_counts: bool = True,
    ) -> FacetedSearchResult:
        """Run faceted search: filter the queryset and compute facet counts.

        When *cache_key* is provided, only the unfiltered base facet set is
        admitted to the Django cache. Active selections are applied to a copy
        of those facets so arbitrary request combinations cannot create keys.

        Result pagination is handled separately without an exact total count.
        """
        started_at = perf_counter()
        base_qs = self._ensure_required_annotations(base_qs)
        selections = self._parse_selections(params)
        filtered_qs = self._apply_filters(base_qs, selections)

        facet_selections = selections if cross_filter_counts else {}
        full_key = self._build_cache_key(cache_key) if cache_key else None

        facets: list[Facet] | None = None
        cache_status = "disabled"
        if full_key:
            facets = django_cache.get(full_key)
            if facets is not None:
                cache_status = "hit"
                logger.debug("Facet cache hit: %s", full_key)

        if facets is None:
            if full_key:
                facets, cache_status = self._get_or_compute_cached_facets(
                    full_key,
                    base_qs,
                )
            else:
                facets = self._compute_facets(base_qs, facet_selections)

        facets = self._apply_selection_state(facets, selections)

        facet_duration_ms = (perf_counter() - started_at) * 1000
        log = logger.info if cache_status == "miss" else logger.debug
        log(
            "Facet resolution cache_status=%s cache_key=%s duration_ms=%.1f",
            cache_status,
            cache_key or "none",
            facet_duration_ms,
        )

        active_filters = self._build_active_filters(selections, facets)

        return FacetedSearchResult(
            queryset=filtered_qs,
            facets=facets,
            active_filters=active_filters,
            cache_status=cache_status,
            facet_duration_ms=facet_duration_ms,
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
        """Extract selections and reject requests exceeding the fixed budget."""
        selections: dict[str, list[str]] = {}
        total_values = 0
        for defn in self.definitions:
            raw_values = params.getlist(defn.name)
            cleaned = list(dict.fromkeys(v.strip() for v in raw_values if v.strip()))
            if defn.allowed_values is not None:
                cleaned = [v for v in cleaned if v in defn.allowed_values]
            if defn.integer_values:
                cleaned = [v for v in cleaned if v.isdigit()]
            if cleaned:
                if len(cleaned) > FACET_MAX_SELECTED_VALUES:
                    message = (
                        f"Facet '{defn.name}' exceeds the maximum of "
                        f"{FACET_MAX_SELECTED_VALUES} selections."
                    )
                    raise FacetSelectionLimitError(message)
                total_values += len(cleaned)
                if total_values > FACET_MAX_TOTAL_SELECTED_VALUES:
                    message = (
                        "The total number of facet selections exceeds the maximum "
                        f"of {FACET_MAX_TOTAL_SELECTED_VALUES}."
                    )
                    raise FacetSelectionLimitError(message)
                selections[defn.name] = cleaned
        return selections

    def _get_or_compute_cached_facets(
        self,
        full_key: str,
        base_qs: QuerySet,
    ) -> tuple[list[Facet], str]:
        """Populate one fixed cache entry while preventing miss stampedes."""
        lock_key = f"{full_key}:lock"
        token = secrets.token_hex(16)
        acquired = django_cache.add(
            lock_key,
            token,
            timeout=FACET_CACHE_LOCK_TIMEOUT,
        )
        if not acquired:
            deadline = monotonic() + FACET_CACHE_LOCK_WAIT_SECONDS
            while monotonic() < deadline:
                facets = django_cache.get(full_key)
                if facets is not None:
                    return facets, "hit-after-wait"
                sleep(0.05)
            message = "Facet counts are currently being refreshed."
            raise FacetCacheBusyError(message)

        try:
            facets = django_cache.get(full_key)
            if facets is not None:
                return facets, "hit-after-lock"
            facets = self._compute_facets(base_qs, {})
            django_cache.set(full_key, facets, FACET_CACHE_TIMEOUT)
            logger.debug("Facet cache set: %s", full_key)
            return facets, "miss"
        finally:
            if django_cache.get(lock_key) == token:
                django_cache.delete(lock_key)

    def _apply_selection_state(
        self,
        facets: list[Facet],
        selections: dict[str, list[str]],
    ) -> list[Facet]:
        """Return request-scoped facet copies without mutating cached values."""
        selected_by_name = {name: set(values) for name, values in selections.items()}
        definitions = {definition.name: definition for definition in self.definitions}
        result: list[Facet] = []
        for facet in facets:
            selected = selected_by_name.get(facet.name, set())
            values = [
                replace(value, selected=value.value in selected)
                for value in facet.values
            ]
            present = {value.value for value in values}
            values.extend(
                FacetValue(value=value, label=value, count=0, selected=True)
                for value in selected - present
            )
            sort_facet_values(values, definitions[facet.name])
            result.append(replace(facet, values=values))
        return result

    def _apply_filters(
        self, qs: QuerySet, selections: dict[str, list[str]]
    ) -> QuerySet:
        """Apply all active facet filters (AND between facets, OR within)."""
        for defn in self.definitions:
            values = selections.get(defn.name)
            if values:
                qs = filter_by_facet(qs, defn, values)
        return qs

    def _compute_facets(
        self,
        base_qs: QuerySet,
        selections: dict[str, list[str]],
    ) -> list[Facet]:
        # Tests patch this method to count database recomputations.
        return compute_facets(self.definitions, base_qs, selections)

    @staticmethod
    def _build_cache_key(base_key: str) -> str:
        """Build the one versioned cache key admitted for a facet scope."""
        version_key = FACET_VERSION_KEYS.get(base_key, f"{base_key}:version")
        version = django_cache.get_or_set(version_key, 1, None)
        return f"{base_key}:v{version}:base"

    @staticmethod
    def invalidate_cache(*cache_keys: str) -> None:
        """Invalidate scoped cached facet counts.

        Bumps a single version counter folded into every facet cache key, so
        every cached combination is invalidated atomically without enumerating
        keys. Stale-version entries fall off via their TTL.
        """
        targets = cache_keys or tuple(FACET_VERSION_KEYS)
        for cache_key in targets:
            version_key = FACET_VERSION_KEYS.get(cache_key, f"{cache_key}:version")
            try:
                django_cache.incr(version_key)
            except ValueError:
                # Version key absent (never set or expired): start a fresh epoch.
                django_cache.set(version_key, 2, None)

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
