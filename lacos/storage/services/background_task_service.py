import logging
from typing import Any, Dict, Optional

from django.utils import timezone

from lacos.storage.models import BackgroundTask


logger = logging.getLogger(__name__)


class BackgroundTaskService:
    """Helper for tracking background task progress."""

    @staticmethod
    def create(task_name: str, *, description: str = '', metadata: Optional[Dict[str, Any]] = None) -> BackgroundTask:
        task = BackgroundTask.objects.create(
            task_name=task_name,
            description=description,
            metadata=metadata or {},
            status=BackgroundTask.Status.QUEUED,
            message='Queued'
        )
        logger.info("Created background task %s (%s)", task.id, task_name)
        return task

    @staticmethod
    def attach_huey_id(task_id: str | BackgroundTask, huey_task_id: str) -> None:
        task = BackgroundTaskService._get_task_or_none(task_id)
        if not task:
            return
        task.huey_task_id = huey_task_id
        task.save(update_fields=['huey_task_id', 'updated_at'])

    @staticmethod
    def mark_running(task_id: str | BackgroundTask, message: Optional[str] = None) -> None:
        task = BackgroundTaskService._get_task_or_none(task_id)
        if not task:
            return
        task.mark_running(message)

    @staticmethod
    def mark_success(
        task_id: str | BackgroundTask,
        *,
        message: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        task = BackgroundTaskService._get_task_or_none(task_id)
        if not task:
            return
        task.mark_success(message, result)

    @staticmethod
    def mark_failed(
        task_id: str | BackgroundTask,
        error_message: str,
        *,
        result: Optional[Dict[str, Any]] = None
    ) -> None:
        task = BackgroundTaskService._get_task_or_none(task_id)
        if not task:
            return
        task.mark_failed(error_message, result)

    @staticmethod
    def touch(task_id: str | BackgroundTask, *, message: Optional[str] = None) -> None:
        task = BackgroundTaskService._get_task_or_none(task_id)
        if not task:
            return
        if message is not None:
            task.message = message
        task.updated_at = timezone.now()
        task.save(update_fields=['message', 'updated_at'])

    @staticmethod
    def _get_task_or_none(task_id: str | BackgroundTask) -> BackgroundTask | None:
        if isinstance(task_id, BackgroundTask):
            return task_id
        try:
            return BackgroundTask.objects.get(pk=task_id)
        except BackgroundTask.DoesNotExist:
            logger.warning("Background task %s not found", task_id)
            return None
