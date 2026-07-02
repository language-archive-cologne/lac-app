from __future__ import annotations

from unittest.mock import patch

from lacos.common.background_task_retention_tasks import cleanup_background_tasks


def _call(task_fn):
    return getattr(task_fn, "call_local", task_fn)()


def test_runs_service_when_enabled(settings):
    settings.BACKGROUND_TASK_RETENTION_ENABLED = True

    with patch(
        "lacos.common.background_task_retention_tasks.BackgroundTaskRetentionService"
    ) as service_cls:
        service_cls.return_value.run.return_value = {"success": True, "deleted": 5}
        result = _call(cleanup_background_tasks)

    assert result["deleted"] == 5
    service_cls.return_value.run.assert_called_once()


def test_skips_when_disabled(settings):
    settings.BACKGROUND_TASK_RETENTION_ENABLED = False

    with patch(
        "lacos.common.background_task_retention_tasks.BackgroundTaskRetentionService"
    ) as service_cls:
        result = _call(cleanup_background_tasks)

    assert result == {"success": False, "skipped": "retention_disabled"}
    service_cls.assert_not_called()
