"""Huey tasks that update audio derivative status and ELAN audio links.

These tasks only read S3. They never generate derivatives.
"""

import logging
from collections import Counter

from django.conf import settings
from huey.contrib.djhuey import db_task

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


def _check_hour() -> int:
    return int(getattr(settings, "MEDIA_DERIVATIVE_CHECK_CRON_HOUR", 4))


def _check_minute() -> int:
    return int(getattr(settings, "MEDIA_DERIVATIVE_CHECK_CRON_MINUTE", 30))


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


def _check_all_derivatives() -> dict:
    return recheck_derivative_rows(MediaDerivativeStatus.objects.all())


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
else:

    def check_media_derivatives_periodic() -> dict:  # pragma: no cover - fallback
        return _check_all_derivatives()
