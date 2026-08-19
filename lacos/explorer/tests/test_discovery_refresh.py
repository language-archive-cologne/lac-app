"""Revision and orchestration policy for derived discovery projections."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from lacos.explorer.discovery_refresh import DiscoveryRefreshCoordinator
from lacos.explorer.discovery_refresh import enqueue_discovery_refresh
from lacos.explorer.discovery_refresh import request_discovery_refresh
from lacos.explorer.models import BundleFileTypeFacet
from lacos.explorer.models import DiscoveryIndexState
from lacos.explorer.public_search.store import load_public_search_index
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_bundle_facets import _create_collection

READY_REVISION = 4
DEGRADED_REVISION = 2


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_discovery_refresh_is_marked_only_after_source_transaction_commits(
    django_capture_on_commit_callbacks,
):
    scheduled: list[bool] = []

    with (
        django_capture_on_commit_callbacks(execute=True),
        transaction.atomic(),
    ):
        request_discovery_refresh(enqueue=lambda: scheduled.append(True))
        assert not DiscoveryIndexState.objects.exists()

    state = DiscoveryIndexState.objects.get()
    assert state.source_revision == 1
    assert state.status == DiscoveryIndexState.Status.PENDING
    assert scheduled == [True]


@override_settings(DISCOVERY_REFRESH_ENABLED=False)
@pytest.mark.django_db
def test_disabled_discovery_refresh_does_not_create_state(
    django_capture_on_commit_callbacks,
):
    with django_capture_on_commit_callbacks(execute=True):
        request_discovery_refresh(enqueue=lambda: None)

    assert not DiscoveryIndexState.objects.exists()


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_discovery_coordinator_advances_every_projection_to_source_revision():
    state = DiscoveryIndexState.objects.create(source_revision=READY_REVISION)
    calls: list[str] = []

    coordinator = DiscoveryRefreshCoordinator(
        vector_rebuilder=lambda: calls.append("vectors") or (40, 1444),
        index_builder=lambda: calls.append("index")
        or {"collections": [], "bundles": []},
        index_writer=lambda path, index: calls.append("publish") or "version",
        facet_warmer=lambda refresh: calls.append(f"facets:{refresh}") or [],
    )

    result = coordinator.refresh(force=True)

    state.refresh_from_db()
    assert calls == ["vectors", "index", "publish", "facets:True"]
    assert result.success is True
    assert result.needs_refresh is False
    assert state.search_vector_revision == READY_REVISION
    assert state.public_index_revision == READY_REVISION
    assert state.facet_cache_revision == READY_REVISION
    assert state.status == DiscoveryIndexState.Status.READY
    assert state.last_error == ""


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_projection_failure_keeps_other_refreshes_and_records_degraded_state():
    state = DiscoveryIndexState.objects.create(source_revision=DEGRADED_REVISION)
    calls: list[str] = []

    def fail_vectors():
        calls.append("vectors")
        message = "vector refresh failed"
        raise RuntimeError(message)

    coordinator = DiscoveryRefreshCoordinator(
        vector_rebuilder=fail_vectors,
        index_builder=lambda: calls.append("index")
        or {"collections": [], "bundles": []},
        index_writer=lambda path, index: calls.append("publish") or "version",
        facet_warmer=lambda refresh: calls.append("facets") or [],
    )

    result = coordinator.refresh(force=True)

    state.refresh_from_db()
    assert calls == ["vectors", "index", "publish", "facets"]
    assert result.success is False
    assert state.search_vector_revision == 0
    assert state.public_index_revision == DEGRADED_REVISION
    assert state.facet_cache_revision == DEGRADED_REVISION
    assert state.status == DiscoveryIndexState.Status.DEGRADED
    assert "vector refresh failed" in state.last_error


@override_settings(
    DISCOVERY_REFRESH_ENABLED=True,
    DISCOVERY_REFRESH_DEBOUNCE_SECONDS=30,
)
@pytest.mark.django_db
def test_discovery_coordinator_waits_for_quiet_window():
    DiscoveryIndexState.objects.create(
        source_revision=1,
        dirty_at=timezone.now() - timedelta(seconds=5),
    )
    calls: list[str] = []
    coordinator = DiscoveryRefreshCoordinator(
        vector_rebuilder=lambda: calls.append("vectors"),
        index_builder=lambda: calls.append("index"),
        index_writer=lambda path, index: calls.append("publish"),
        facet_warmer=lambda refresh: calls.append("facets"),
    )

    result = coordinator.refresh(force=False)

    assert result.deferred is True
    assert result.retry_after_seconds > 0
    assert calls == []


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_changes_during_refresh_leave_newer_revision_pending():
    state = DiscoveryIndexState.objects.create(source_revision=1)

    def rebuild_and_change_source():
        DiscoveryIndexState.objects.filter(pk=state.pk).update(source_revision=2)
        return 1, 1

    coordinator = DiscoveryRefreshCoordinator(
        vector_rebuilder=rebuild_and_change_source,
        index_builder=lambda: {"collections": [], "bundles": []},
        index_writer=lambda path, index: "version",
        facet_warmer=lambda refresh: [],
    )

    result = coordinator.refresh(force=True)

    state.refresh_from_db()
    assert result.needs_refresh is True
    assert state.source_revision == DEGRADED_REVISION
    assert state.search_vector_revision == 1
    assert state.public_index_revision == 1
    assert state.facet_cache_revision == 1
    assert state.status == DiscoveryIndexState.Status.PENDING


@override_settings(
    DISCOVERY_REFRESH_ENABLED=True,
    DISCOVERY_REFRESH_DEBOUNCE_SECONDS=30,
)
@pytest.mark.django_db
def test_discovery_enqueue_is_deduplicated_in_shared_cache():
    cache.clear()

    with patch(
        "lacos.explorer.tasks.refresh_discovery_projections_task.schedule",
    ) as schedule:
        first = enqueue_discovery_refresh()
        second = enqueue_discovery_refresh()

    assert first is True
    assert second is False
    schedule.assert_called_once_with(delay=30)


@pytest.mark.django_db
def test_refresh_command_builds_all_real_projections(tmp_path):
    collection = _create_collection("refresh-collection", "Refresh Collection")
    _create_bundle("refresh-bundle", "Refresh Bundle", collection)
    target = tmp_path / "public-search.json"
    stdout = StringIO()

    with override_settings(
        DISCOVERY_REFRESH_ENABLED=True,
        PUBLIC_SEARCH_INDEX_PATH=target,
    ):
        call_command("refresh_discovery_search", force=True, stdout=stdout)

    state = DiscoveryIndexState.objects.get()
    index = load_public_search_index(target)
    assert state.status == DiscoveryIndexState.Status.READY
    assert state.search_vector_revision == state.source_revision == 1
    assert state.public_index_revision == 1
    assert state.facet_cache_revision == 1
    assert index["bundles"][0]["identifier"] == "refresh-bundle"
    assert "Discovery projections refreshed" in stdout.getvalue()


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_existing_metadata_signals_mark_discovery_revision_dirty(
    django_capture_on_commit_callbacks,
):
    with (
        patch("lacos.explorer.discovery_refresh.enqueue_discovery_refresh") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        _create_collection("signal-collection", "Signal Collection")

    state = DiscoveryIndexState.objects.get()
    assert state.source_revision > 0
    assert state.status == DiscoveryIndexState.Status.PENDING
    assert enqueue.called


@override_settings(DISCOVERY_REFRESH_ENABLED=True)
@pytest.mark.django_db
def test_file_type_projection_change_marks_discovery_revision_dirty(
    django_capture_on_commit_callbacks,
):
    collection = _create_collection("file-type-collection", "File Type Collection")
    bundle = _create_bundle("file-type-bundle", "File Type Bundle", collection)
    DiscoveryIndexState.objects.all().delete()

    with (
        patch("lacos.explorer.discovery_refresh.enqueue_discovery_refresh") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        BundleFileTypeFacet.objects.create(
            collection=collection,
            bundle=bundle,
            file_type="wav",
        )

    state = DiscoveryIndexState.objects.get()
    assert state.source_revision == 1
    enqueue.assert_called_once()
