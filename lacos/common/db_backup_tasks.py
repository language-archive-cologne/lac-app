from __future__ import annotations

import logging

from django.conf import settings
from huey.contrib.djhuey import task

try:
    from huey.contrib.djhuey import crontab
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


@task(retries=2, retry_delay=300)
def backup_database_to_s3() -> dict:
    if not _backup_enabled():
        return {"success": False, "skipped": "db_backup_disabled"}

    service = DatabaseBackupService()
    result = service.run()
    if not result.get("success"):
        logger.error("Database backup task failed: %s", result)
    return result


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(crontab(minute=_backup_minute(), hour=_backup_hour()))
    def backup_database_to_s3_periodic() -> dict:
        return backup_database_to_s3()
else:
    def backup_database_to_s3_periodic() -> dict:  # pragma: no cover - fallback
        return backup_database_to_s3()
