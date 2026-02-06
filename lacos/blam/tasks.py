from __future__ import annotations

import logging

from huey.contrib.djhuey import task

from lacos.common.services.database_backup_service import DatabaseBackupService
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


@task(retries=1, retry_delay=60)
def reindex_search_vectors_task(tracking_id: str) -> dict:
    """Rebuild BLAM search vectors and persist status to BackgroundTask."""
    BackgroundTaskService.mark_running(tracking_id, message="Rebuilding search vectors")
    try:
        collections_count, bundles_count = rebuild_all_search_vectors()
        payload = {
            "success": True,
            "collections_reindexed": collections_count,
            "bundles_reindexed": bundles_count,
        }
        BackgroundTaskService.mark_success(
            tracking_id,
            message=(
                f"Reindex completed. Updated {collections_count} collections "
                f"and {bundles_count} bundles."
            ),
            result=payload,
        )
        return payload
    except Exception as exc:
        logger.error("Failed to rebuild search vectors: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload


@task(retries=1, retry_delay=300)
def backup_database_task(tracking_id: str) -> dict:
    """Create DB dump and upload to S3, tracked by BackgroundTask."""
    BackgroundTaskService.mark_running(tracking_id, message="Creating database backup")
    try:
        result = DatabaseBackupService().run()
        if result.get("success"):
            message = (
                "Backup uploaded to S3."
                f" File: {result.get('backup_file', 'unknown')}"
            )
            BackgroundTaskService.mark_success(
                tracking_id,
                message=message,
                result=result,
            )
        else:
            error_message = result.get("detail") or result.get("error") or "Database backup failed."
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=error_message,
                result=result,
            )
        return result
    except Exception as exc:
        logger.error("Failed to run database backup task: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload
