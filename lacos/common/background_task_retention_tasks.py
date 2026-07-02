from __future__ import annotations

import logging

from django.conf import settings
from huey.contrib.djhuey import task

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task

    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency guard
    HUEY_PERIODIC_AVAILABLE = False

from lacos.common.services.background_task_retention_service import (
    BackgroundTaskRetentionService,
)

logger = logging.getLogger(__name__)


def _retention_enabled() -> bool:
    return bool(getattr(settings, "BACKGROUND_TASK_RETENTION_ENABLED", False))


def _retention_hour() -> int:
    return int(getattr(settings, "BACKGROUND_TASK_RETENTION_CRON_HOUR", 4))


def _retention_minute() -> int:
    return int(getattr(settings, "BACKGROUND_TASK_RETENTION_CRON_MINUTE", 30))


def _run_retention(*, trigger: str = "manual") -> dict:
    """Shared retention logic used by both the manual and periodic tasks."""
    if not _retention_enabled():
        logger.info("Background task retention skipped (disabled), trigger=%s", trigger)
        return {"success": False, "skipped": "retention_disabled"}

    result = BackgroundTaskRetentionService().run()
    logger.info("Background task retention finished, trigger=%s, result=%s", trigger, result)
    return result


@task(retries=1, retry_delay=60)
def cleanup_background_tasks() -> dict:
    return _run_retention(trigger="manual")


if HUEY_PERIODIC_AVAILABLE:
    # Runs daily. Deliberately NOT wrapped in tracked_periodic: it would create a
    # BackgroundTask row on every run, adding to the very table it prunes.
    @db_periodic_task(crontab(minute=_retention_minute(), hour=_retention_hour()))
    def cleanup_background_tasks_periodic() -> dict:
        return _run_retention(trigger="periodic")
else:
    def cleanup_background_tasks_periodic() -> dict:  # pragma: no cover - fallback
        return _run_retention(trigger="periodic")
