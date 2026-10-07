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

from lacos.common.periodic_task_tracker import tracked_periodic
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

    environment = getattr(settings, "DB_BACKUP_ENVIRONMENT", "local")
    logger.info(
        "Database backup started, environment=%s, trigger=%s",
        environment,
        trigger,
    )
    # One ERROR per failed run on this logger. Production routes it to mail_admins.
    try:
        result = DatabaseBackupService().run()
    except Exception:
        logger.exception(
            "Database backup failed, environment=%s, trigger=%s",
            environment,
            trigger,
        )
        raise
    if result.get("success"):
        logger.info(
            "Database backup succeeded, environment=%s, trigger=%s, key=%s",
            environment,
            trigger,
            result.get("key"),
        )
    else:
        logger.error(
            "Database backup failed, environment=%s, trigger=%s, error=%s",
            environment,
            trigger,
            result,
        )
    return result


@task(retries=2, retry_delay=300)
def backup_database_to_s3() -> dict:
    return _run_backup(trigger="manual")


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(crontab(minute=_backup_minute(), hour=_backup_hour()))
    @tracked_periodic(
        task_name="periodic_backup",
        description="Database Backup (periodic)",
        schedule="0 2 * * *",
    )
    def backup_database_to_s3_periodic() -> dict:
        logger.info("Periodic database backup triggered (schedule: %02d:%02d)", _backup_hour(), _backup_minute())
        return _run_backup(trigger="periodic")
else:
    def backup_database_to_s3_periodic() -> dict:  # pragma: no cover - fallback
        return _run_backup(trigger="periodic")
