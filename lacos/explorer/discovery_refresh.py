"""Revision policy and coordination for derived discovery projections."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from lacos.explorer.models import DiscoveryIndexState
from lacos.explorer.public_search.builder import build_public_search_index
from lacos.explorer.public_search.store import write_public_search_index
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.explorer.services.facet_cache_warmer import warm_explorer_facet_caches

logger = logging.getLogger(__name__)

DISCOVERY_REFRESH_SCHEDULED_KEY = "explorer:discovery-refresh:scheduled"


@dataclass(frozen=True)
class DiscoveryRefreshResult:
    success: bool
    target_revision: int
    needs_refresh: bool = False
    deferred: bool = False
    retry_after_seconds: int = 0
    public_index_version: str = ""
    errors: tuple[str, ...] = ()


def request_discovery_refresh(*, enqueue: Callable[[], None] | None = None) -> None:
    """Mark discovery projections dirty after the source transaction commits."""
    if not settings.DISCOVERY_REFRESH_ENABLED:
        return
    scheduler = enqueue or enqueue_discovery_refresh
    transaction.on_commit(lambda: _mark_dirty_and_schedule(scheduler))


def _mark_dirty_and_schedule(scheduler: Callable[[], None]) -> None:
    state, _created = DiscoveryIndexState.objects.get_or_create()
    DiscoveryIndexState.objects.filter(pk=state.pk).update(
        source_revision=F("source_revision") + 1,
        status=DiscoveryIndexState.Status.PENDING,
        dirty_at=timezone.now(),
    )
    scheduler()


def enqueue_discovery_refresh(*, delay_seconds: int | None = None) -> bool:
    """Schedule at most one delayed discovery refresh task."""
    if not settings.DISCOVERY_REFRESH_ENABLED:
        return False
    delay = (
        settings.DISCOVERY_REFRESH_DEBOUNCE_SECONDS
        if delay_seconds is None
        else max(1, delay_seconds)
    )
    timeout = max(300, delay * 4)
    if not cache.add(DISCOVERY_REFRESH_SCHEDULED_KEY, "scheduled", timeout=timeout):
        return False

    from lacos.explorer.tasks import refresh_discovery_projections_task

    refresh_discovery_projections_task.schedule(delay=delay)
    return True


class DiscoveryRefreshCoordinator:
    """Refresh independent search projections to one captured source revision."""

    def __init__(
        self,
        *,
        vector_rebuilder: Callable[[], Any] = rebuild_all_search_vectors,
        index_builder: Callable[[], dict[str, Any]] = build_public_search_index,
        index_writer: Callable[[Path, dict[str, Any]], str] = (
            write_public_search_index
        ),
        facet_warmer: Callable[[bool], Any] = warm_explorer_facet_caches,
    ):
        self.vector_rebuilder = vector_rebuilder
        self.index_builder = index_builder
        self.index_writer = index_writer
        self.facet_warmer = facet_warmer

    def refresh(self, *, force: bool = False) -> DiscoveryRefreshResult:
        state, _created = DiscoveryIndexState.objects.get_or_create()
        if force and state.source_revision == 0:
            state.source_revision = 1
            state.dirty_at = timezone.now()
            state.status = DiscoveryIndexState.Status.PENDING
            state.save(update_fields=["source_revision", "dirty_at", "status"])

        retry_after = self._quiet_window_retry_after(state, force=force)
        if retry_after:
            return DiscoveryRefreshResult(
                success=False,
                target_revision=state.source_revision,
                deferred=True,
                retry_after_seconds=retry_after,
            )

        target_revision = state.source_revision
        state.status = DiscoveryIndexState.Status.REFRESHING
        state.refresh_started_at = timezone.now()
        state.last_error = ""
        state.save(update_fields=["status", "refresh_started_at", "last_error"])

        errors: list[str] = []
        public_version = state.public_index_version

        if self._run_projection("search vectors", self.vector_rebuilder, errors):
            state.search_vector_revision = target_revision

        index_result = self._run_index_projection(errors)
        if index_result is not None:
            public_version = index_result
            state.public_index_revision = target_revision
            state.public_index_version = public_version

        if self._run_projection(
            "facet cache",
            lambda: self.facet_warmer(refresh=True),
            errors,
        ):
            state.facet_cache_revision = target_revision

        latest_source_revision = DiscoveryIndexState.objects.values_list(
            "source_revision",
            flat=True,
        ).get(pk=state.pk)
        needs_refresh = latest_source_revision > target_revision
        state.status = self._completion_status(
            errors,
            needs_refresh=needs_refresh,
        )
        state.last_error = "; ".join(errors)
        state.refresh_completed_at = timezone.now()
        state.save(
            update_fields=[
                "search_vector_revision",
                "public_index_revision",
                "facet_cache_revision",
                "public_index_version",
                "status",
                "last_error",
                "refresh_completed_at",
            ],
        )
        return DiscoveryRefreshResult(
            success=not errors,
            target_revision=target_revision,
            needs_refresh=needs_refresh,
            public_index_version=public_version,
            errors=tuple(errors),
        )

    @staticmethod
    def _quiet_window_retry_after(
        state: DiscoveryIndexState,
        *,
        force: bool,
    ) -> int:
        if force or state.dirty_at is None:
            return 0
        quiet_seconds = settings.DISCOVERY_REFRESH_DEBOUNCE_SECONDS
        age = (timezone.now() - state.dirty_at).total_seconds()
        return max(0, ceil(quiet_seconds - age))

    def _run_index_projection(self, errors: list[str]) -> str | None:
        try:
            outermost = not connection.in_atomic_block
            with transaction.atomic():
                if outermost:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
                        )
                index = self.index_builder()
            return self.index_writer(
                Path(settings.PUBLIC_SEARCH_INDEX_PATH),
                index,
            )
        except Exception as error:  # noqa: BLE001 -- projections fail independently.
            self._record_projection_error("public index", error, errors)
            return None

    @staticmethod
    def _run_projection(
        label: str,
        operation: Callable[[], Any],
        errors: list[str],
    ) -> bool:
        try:
            operation()
        except Exception as error:  # noqa: BLE001 -- projections fail independently.
            DiscoveryRefreshCoordinator._record_projection_error(
                label,
                error,
                errors,
            )
            return False
        return True

    @staticmethod
    def _record_projection_error(
        label: str,
        error: Exception,
        errors: list[str],
    ) -> None:
        message = f"{label}: {error}"
        errors.append(message)
        logger.exception("Discovery projection failed: %s", label)

    @staticmethod
    def _completion_status(
        errors: list[str],
        *,
        needs_refresh: bool,
    ) -> str:
        if errors:
            return DiscoveryIndexState.Status.DEGRADED
        if needs_refresh:
            return DiscoveryIndexState.Status.PENDING
        return DiscoveryIndexState.Status.READY
