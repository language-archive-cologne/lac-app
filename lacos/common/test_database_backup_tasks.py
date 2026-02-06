from __future__ import annotations

from unittest.mock import patch

from lacos.common.db_backup_tasks import backup_database_to_s3


def test_backup_database_to_s3_runs_service_when_enabled(settings):
    settings.DB_BACKUP_ENABLED = True

    with patch("lacos.common.db_backup_tasks.DatabaseBackupService") as service_cls:
        service_cls.return_value.run.return_value = {"success": True, "key": "db-backups/file.sql.gz"}
        runner = getattr(backup_database_to_s3, "call_local", backup_database_to_s3)
        result = runner()

    assert result["success"] is True
    service_cls.assert_called_once()
    service_cls.return_value.run.assert_called_once()


def test_backup_database_to_s3_skips_when_disabled(settings):
    settings.DB_BACKUP_ENABLED = False

    with patch("lacos.common.db_backup_tasks.DatabaseBackupService") as service_cls:
        runner = getattr(backup_database_to_s3, "call_local", backup_database_to_s3)
        result = runner()

    assert result == {"success": False, "skipped": "db_backup_disabled"}
    service_cls.assert_not_called()
