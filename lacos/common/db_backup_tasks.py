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

from lacos.common.services.database_backup_service import DatabaseBackupService

logger = logging.getLogger(__name__)


def _backup_enabled() -> bool:
    return bool(getattr(settings, "DB_BACKUP_ENABLED", False))


def _backup_hour() -> int:
    return int(getattr(settings, "DB_BACKUP_CRON_HOUR", 2))


def _backup_minute() -> int:
    return int(getattr(settings, "DB_BACKUP_CRON_MINUTE", 0))


def _run_backup(*, trigger: str = "manual") -> dict:
    """Shared backup logic used by both manual and periodic tasks."""
    if not _backup_enabled():
        logger.info("Database backup skipped (disabled), trigger=%s", trigger)
        return {"success": False, "skipped": "db_backup_disabled"}

    logger.info("Database backup started, trigger=%s", trigger)
    service = DatabaseBackupService()
    result = service.run()
    if result.get("success"):
        logger.info("Database backup succeeded, trigger=%s, key=%s", trigger, result.get("key"))
    else:
        logger.error("Database backup failed, trigger=%s, error=%s", trigger, result)
    return result


@task(retries=2, retry_delay=300)
def backup_database_to_s3() -> dict:
    return _run_backup(trigger="manual")


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(crontab(minute=_backup_minute(), hour=_backup_hour()))
    def backup_database_to_s3_periodic() -> dict:
        logger.info("Periodic database backup triggered (schedule: %02d:%02d)", _backup_hour(), _backup_minute())
        return _run_backup(trigger="periodic")
else:
    def backup_database_to_s3_periodic() -> dict:  # pragma: no cover - fallback
        return _run_backup(trigger="periodic")
