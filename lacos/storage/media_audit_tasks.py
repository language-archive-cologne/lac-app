"""Huey tasks that update audio derivative status and ELAN audio links.

These tasks only read S3. They never generate derivatives.
"""

import logging
from collections import Counter

from django.conf import settings
from huey.contrib.djhuey import HUEY
from huey.contrib.djhuey import db_task
from huey.exceptions import TaskLockedException

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task

    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    HUEY_PERIODIC_AVAILABLE = False

from lacos.common.periodic_task_tracker import tracked_periodic
from lacos.storage.models import ElanMediaLink
from lacos.storage.models import MediaDerivativeStatus
from lacos.storage.services.media_derivative_recorder import record_check
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)

# The nightly check and the weekly audit write the same rows. They share one
# lock, so they never run at the same time. The task that finds the lock
# taken skips its run. The consumer clears the lock when it starts
# (``flush_locks``), so a killed worker does not block the tasks.
media_status_lock = HUEY.lock_task("media-derivative-status")
SKIPPED_LOCKED = {"success": False, "skipped": "media_status_task_running"}


def _check_hour() -> int:
    return int(getattr(settings, "MEDIA_DERIVATIVE_CHECK_CRON_HOUR", 4))


def _check_minute() -> int:
    return int(getattr(settings, "MEDIA_DERIVATIVE_CHECK_CRON_MINUTE", 30))


def _audit_day_of_week() -> str:
    return str(getattr(settings, "MEDIA_AUDIT_CRON_DAY_OF_WEEK", "0"))


def _audit_hour() -> int:
    return int(getattr(settings, "MEDIA_AUDIT_CRON_HOUR", 3))


def _audit_minute() -> int:
    return int(getattr(settings, "MEDIA_AUDIT_CRON_MINUTE", 30))


def recheck_derivative_rows(queryset) -> dict:
    """Update each row from HEAD requests. Errors on one row do not stop the run."""
    media_service = MediaProcessingService()
    counts: Counter = Counter()
    for row in queryset.order_by("bucket", "s3_key").iterator():
        try:
            updated = record_check(row.bucket, row.s3_key, media_service=media_service)
            counts[updated.status] += 1
        except Exception as exc:
            counts["errors"] += 1
            logger.error(
                "Derivative check failed for %s/%s: %s", row.bucket, row.s3_key, exc
            )
    return {"success": counts["errors"] == 0, **counts}


@db_task(retries=1, retry_delay=60)
def recheck_derivatives_task(row_ids: list[str]) -> dict:
    return recheck_derivative_rows(MediaDerivativeStatus.objects.filter(id__in=row_ids))


@db_task(retries=1, retry_delay=60)
def recheck_elan_links_task(link_ids: list[str]) -> dict:
    from lacos.storage.services.media_audit_service import MediaAuditService

    service = MediaAuditService()
    errors = 0
    links = ElanMediaLink.objects.filter(id__in=link_ids).select_related(
        "bundle", "collection"
    )
    for link in links:
        resource = link.elan_resource
        if resource is None:
            link.delete()
            continue
        try:
            service.audit_elan_resource(link.bundle, resource, link.collection)
        except Exception as exc:
            errors += 1
            logger.error("ELAN link check failed for %s: %s", link.elan_file_name, exc)
    return {"success": errors == 0, "errors": errors, **service.counts}


def _run_locked(name: str, run) -> dict:
    try:
        with media_status_lock:
            return run()
    except TaskLockedException:
        logger.warning("%s skipped: another media status task is running", name)
        return dict(SKIPPED_LOCKED)


def _check_all_derivatives() -> dict:
    return _run_locked(
        "Media derivative check",
        lambda: recheck_derivative_rows(MediaDerivativeStatus.objects.all()),
    )


def _audit_all_collections() -> dict:
    from lacos.storage.services.media_audit_service import MediaAuditService

    def run() -> dict:
        counts = MediaAuditService().audit_all_collections()
        return {"success": counts["collection_errors"] == 0, **counts}

    return _run_locked("Media audit", run)


if HUEY_PERIODIC_AVAILABLE:

    @db_periodic_task(crontab(minute=_check_minute(), hour=_check_hour()))
    @tracked_periodic(
        task_name="periodic_media_derivative_check",
        description="Media Derivative Check (periodic)",
        schedule=f"{_check_minute()} {_check_hour()} * * *",
    )
    def check_media_derivatives_periodic() -> dict:
        """Update the status of all recorded audio objects. Generate nothing."""
        return _check_all_derivatives()

    @db_periodic_task(
        crontab(
            minute=_audit_minute(), hour=_audit_hour(), day_of_week=_audit_day_of_week()
        )
    )
    @tracked_periodic(
        task_name="periodic_media_audit",
        description="Media Audit of all collections (periodic)",
        schedule=f"{_audit_minute()} {_audit_hour()} * * {_audit_day_of_week()}",
    )
    def audit_media_periodic() -> dict:
        """Audit all collections, so new audio and ELAN files get rows."""
        return _audit_all_collections()
else:

    def check_media_derivatives_periodic() -> dict:  # pragma: no cover - fallback
        return _check_all_derivatives()

    def audit_media_periodic() -> dict:  # pragma: no cover - fallback
        return _audit_all_collections()
