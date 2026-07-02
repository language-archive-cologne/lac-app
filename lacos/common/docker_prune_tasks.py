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

from lacos.common.services.docker_prune_service import DockerPruneService

logger = logging.getLogger(__name__)


def _prune_enabled() -> bool:
    return bool(getattr(settings, "DOCKER_PRUNE_ENABLED", False))


def _prune_minute() -> int:
    return int(getattr(settings, "DOCKER_PRUNE_CRON_MINUTE", 0))


def _run_prune(*, trigger: str = "manual", force: bool = False) -> dict:
    """Shared prune logic used by both the manual and periodic tasks."""
    if not _prune_enabled():
        logger.info("Docker prune skipped (disabled), trigger=%s", trigger)
        return {"success": False, "skipped": "docker_prune_disabled"}

    logger.info("Docker prune started, trigger=%s, force=%s", trigger, force)
    result = DockerPruneService().run(force=force)
    if result.get("success"):
        logger.info("Docker prune finished, trigger=%s, result=%s", trigger, result)
    else:
        logger.error("Docker prune failed, trigger=%s, result=%s", trigger, result)
    return result


@task(retries=1, retry_delay=60)
def prune_docker_resources() -> dict:
    # Manual trigger always prunes, regardless of the disk threshold.
    return _run_prune(trigger="manual", force=True)


if HUEY_PERIODIC_AVAILABLE:
    # Runs hourly and only prunes when disk usage is above the threshold, so it
    # is a cheap no-op most of the time. It deliberately does NOT create a
    # BackgroundTask record per run (unlike the daily backup) because there is no
    # retention for those rows and an hourly janitor would accumulate them
    # indefinitely; outcomes are logged via DockerPruneService instead.
    @db_periodic_task(crontab(minute=_prune_minute()))
    def prune_docker_resources_periodic() -> dict:
        return _run_prune(trigger="periodic", force=False)
else:
    def prune_docker_resources_periodic() -> dict:  # pragma: no cover - fallback
        return _run_prune(trigger="periodic", force=False)
