from __future__ import annotations

from unittest.mock import patch

import pytest

from lacos.blam.tasks import backup_database_task
from lacos.blam.tasks import reindex_search_vectors_task
from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService


@pytest.mark.django_db
@patch("lacos.blam.tasks.rebuild_all_search_vectors")
def test_reindex_search_vectors_task_marks_success(mock_rebuild):
    mock_rebuild.return_value = (4, 7)
    task_record = BackgroundTaskService.create(task_name="blam_reindex_search_vectors")

    runner = getattr(reindex_search_vectors_task, "call_local", reindex_search_vectors_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is True
    assert result["collections_reindexed"] == 4
    assert result["bundles_reindexed"] == 7
    assert task_record.status == BackgroundTask.Status.SUCCESS
    assert task_record.result["collections_reindexed"] == 4


@pytest.mark.django_db
@patch("lacos.blam.tasks.rebuild_all_search_vectors")
def test_reindex_search_vectors_task_marks_failure(mock_rebuild):
    mock_rebuild.side_effect = RuntimeError("reindex failed")
    task_record = BackgroundTaskService.create(task_name="blam_reindex_search_vectors")

    runner = getattr(reindex_search_vectors_task, "call_local", reindex_search_vectors_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is False
    assert task_record.status == BackgroundTask.Status.FAILED
    assert "reindex failed" in task_record.error


@pytest.mark.django_db
@patch("lacos.blam.tasks.DatabaseBackupService")
def test_backup_database_task_marks_success(mock_backup_service):
    mock_backup_service.return_value.run.return_value = {
        "success": True,
        "backup_file": "backup_2026_02_06T02_00_00.sql.gz",
        "bucket": "backups",
        "key": "db-backups/backup_2026_02_06T02_00_00.sql.gz",
    }
    task_record = BackgroundTaskService.create(task_name="blam_database_backup")

    runner = getattr(backup_database_task, "call_local", backup_database_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is True
    assert task_record.status == BackgroundTask.Status.SUCCESS
    assert task_record.result["bucket"] == "backups"


@pytest.mark.django_db
@patch("lacos.blam.tasks.DatabaseBackupService")
def test_backup_database_task_marks_failure(mock_backup_service):
    mock_backup_service.return_value.run.return_value = {
        "success": False,
        "error": "backup_command_failed",
    }
    task_record = BackgroundTaskService.create(task_name="blam_database_backup")

    runner = getattr(backup_database_task, "call_local", backup_database_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is False
    assert task_record.status == BackgroundTask.Status.FAILED
    assert "backup_command_failed" in task_record.error
