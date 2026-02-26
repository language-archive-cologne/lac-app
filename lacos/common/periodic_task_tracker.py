"""Wrapper that adds BackgroundTask tracking to periodic huey tasks."""
from __future__ import annotations

import logging
import time
from functools import wraps

from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


def tracked_periodic(task_name: str, description: str, schedule: str):
    """Decorator that wraps a periodic task to create BackgroundTask records.

    Args:
        task_name: BackgroundTask.task_name value (e.g. "periodic_backup")
        description: Human-readable description
        schedule: Cron expression string for metadata (e.g. "0 2 * * *")
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            task_record = BackgroundTaskService.create(
                task_name=task_name,
                description=description,
                metadata={"trigger": "periodic", "schedule": schedule},
            )
            BackgroundTaskService.mark_running(task_record, message=f"Running {description}")
            start = time.monotonic()
            try:
                result = fn(*args, **kwargs)
                elapsed = round(time.monotonic() - start, 1)
                success = result.get("success", True) if isinstance(result, dict) else True
                if success:
                    BackgroundTaskService.mark_success(
                        task_record,
                        message=f"Completed in {elapsed}s",
                        result=result if isinstance(result, dict) else None,
                    )
                else:
                    error_msg = result.get("error", result.get("skipped", "Unknown error")) if isinstance(result, dict) else "Failed"
                    BackgroundTaskService.mark_failed(
                        task_record,
                        error_message=str(error_msg),
                        result=result if isinstance(result, dict) else None,
                    )
                return result
            except Exception as exc:
                elapsed = round(time.monotonic() - start, 1)
                BackgroundTaskService.mark_failed(
                    task_record,
                    error_message=f"{exc} (after {elapsed}s)",
                )
                raise
        return wrapper
    return decorator
