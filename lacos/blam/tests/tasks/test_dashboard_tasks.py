from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from lacos.blam.tasks import backup_database_task
from lacos.blam.tasks import reindex_collections_task
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


@pytest.mark.django_db
@patch("lacos.blam.tasks.call_command")
def test_reindex_collections_task_marks_success(mock_call_command):
    def fake_call_command(*args, **kwargs):
        out: StringIO = kwargs["stdout"]
        out.write("Reindexed collection 1 from bucket/key\n")
        out.write("Reindexed bundle 10 (resources 11)\n")
        out.write("Reindexed bundle 12 (resources 13)\n")
        out.write("Skipped unchanged collection 2 from bucket/key\n")
        out.write("Skipped unchanged bundle 14 (resources 15)\n")

    mock_call_command.side_effect = fake_call_command
    task_record = BackgroundTaskService.create(task_name="blam_reindex_collections")

    runner = getattr(reindex_collections_task, "call_local", reindex_collections_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is True
    assert result["collections_reindexed"] == 1
    assert result["bundles_reindexed"] == 2
    assert result["collections_skipped"] == 1
    assert result["bundles_skipped"] == 1
    assert result["collection_failures"] == 0
    assert result["bundle_failures"] == 0
    assert task_record.status == BackgroundTask.Status.SUCCESS
    mock_call_command.assert_called_once()
    args, kwargs = mock_call_command.call_args
    assert args == ("reindex_collection", "--all", "--update-bundles")
    assert "stdout" in kwargs
    assert result["force"] is False
    assert result["mode"] == "incremental"


@pytest.mark.django_db
@patch("lacos.blam.tasks.call_command")
def test_reindex_collections_task_can_force_full_reindex(mock_call_command):
    def fake_call_command(*args, **kwargs):
        out: StringIO = kwargs["stdout"]
        out.write("Reindexed collection 1 from bucket/key\n")

    mock_call_command.side_effect = fake_call_command
    task_record = BackgroundTaskService.create(task_name="blam_force_reindex_collections")

    runner = getattr(reindex_collections_task, "call_local", reindex_collections_task)
    result = runner(str(task_record.id), force=True)

    args, kwargs = mock_call_command.call_args
    assert args == ("reindex_collection", "--all", "--update-bundles", "--force")
    assert "stdout" in kwargs
    assert result["force"] is True
    assert result["mode"] == "forced"


@pytest.mark.django_db
@patch("lacos.blam.tasks.call_command")
def test_reindex_collections_task_marks_failure_when_command_has_errors(mock_call_command):
    def fake_call_command(*args, **kwargs):
        out: StringIO = kwargs["stdout"]
        out.write("Reindexed collection 1 from bucket/key\n")
        out.write("Failed to reindex bundle from bucket/key\n")

    mock_call_command.side_effect = fake_call_command
    task_record = BackgroundTaskService.create(task_name="blam_reindex_collections")

    runner = getattr(reindex_collections_task, "call_local", reindex_collections_task)
    result = runner(str(task_record.id))
    task_record.refresh_from_db()

    assert result["success"] is False
    assert result["bundle_failures"] == 1
    assert task_record.status == BackgroundTask.Status.FAILED
