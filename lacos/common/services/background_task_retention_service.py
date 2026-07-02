from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from lacos.storage.models import BackgroundTask

logger = logging.getLogger(__name__)


class BackgroundTaskRetentionService:
    """Delete old ``BackgroundTask`` rows to bound unbounded table growth.

    Frequent periodic tasks (e.g. upload verification, every 15 min) create a row
    per run, which accumulates indefinitely. This service deletes rows older than
    ``BACKGROUND_TASK_RETENTION_DAYS`` while always keeping the single most recent
    row per ``task_name`` — so the admin dashboard's "last run" signal is never
    lost, even for tasks that run less often than the retention window.
    """

    def __init__(self, *, now_fn=None) -> None:
        self.retention_days = int(getattr(settings, "BACKGROUND_TASK_RETENTION_DAYS", 30))
        self.now_fn = now_fn or timezone.now

    def run(self) -> dict:
        cutoff = self.now_fn() - timedelta(days=self.retention_days)

        # Postgres DISTINCT ON: newest row id for each task_name, always retained.
        keep_ids = list(
            BackgroundTask.objects.order_by("task_name", "-created_at")
            .distinct("task_name")
            .values_list("id", flat=True)
        )

        deleted, _ = (
            BackgroundTask.objects.filter(created_at__lt=cutoff)
            .exclude(id__in=keep_ids)
            .delete()
        )
        logger.info(
            "BackgroundTaskRetentionService: deleted %d rows older than %s (kept %d latest-per-task)",
            deleted, cutoff.isoformat(), len(keep_ids),
        )
        return {
            "success": True,
            "deleted": deleted,
            "cutoff": cutoff.isoformat(),
            "kept_latest": len(keep_ids),
        }
