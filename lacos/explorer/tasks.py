"""Huey tasks for keeping derived discovery projections synchronized."""

from __future__ import annotations

import secrets
from dataclasses import asdict

from django.conf import settings
from django.core.cache import cache
from huey import crontab
from huey.contrib.djhuey import db_periodic_task
from huey.contrib.djhuey import task

from lacos.explorer.discovery_refresh import DISCOVERY_REFRESH_SCHEDULED_KEY
from lacos.explorer.discovery_refresh import DiscoveryRefreshCoordinator
from lacos.explorer.discovery_refresh import enqueue_discovery_refresh

DISCOVERY_REFRESH_LOCK_KEY = "explorer:discovery-refresh:lock"
DISCOVERY_REFRESH_LOCK_TIMEOUT = 60 * 30


@task(retries=1, retry_delay=60)
def refresh_discovery_projections_task(*, force: bool = False) -> dict:
    cache.delete(DISCOVERY_REFRESH_SCHEDULED_KEY)
    if not settings.DISCOVERY_REFRESH_ENABLED:
        return {"success": False, "skipped": "disabled"}

    token = secrets.token_hex(16)
    if not cache.add(
        DISCOVERY_REFRESH_LOCK_KEY,
        token,
        timeout=DISCOVERY_REFRESH_LOCK_TIMEOUT,
    ):
        enqueue_discovery_refresh(delay_seconds=30)
        return {"success": False, "deferred": True, "reason": "locked"}

    try:
        result = DiscoveryRefreshCoordinator().refresh(force=force)
    finally:
        if cache.get(DISCOVERY_REFRESH_LOCK_KEY) == token:
            cache.delete(DISCOVERY_REFRESH_LOCK_KEY)

    if result.deferred:
        enqueue_discovery_refresh(delay_seconds=result.retry_after_seconds)
    elif result.needs_refresh:
        enqueue_discovery_refresh()
    return asdict(result)


@db_periodic_task(crontab(minute="17"))
def reconcile_discovery_projections() -> dict:
    """Hourly safety reconciliation for missed dirty notifications."""
    return refresh_discovery_projections_task.call_local(force=True)
