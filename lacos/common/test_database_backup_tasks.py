from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from django.utils.log import AdminEmailHandler

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


BACKUP_LOGGER = "lacos.common.db_backup_tasks"


def _backup_errors(caplog):
    return [
        record
        for record in caplog.records
        if record.name == BACKUP_LOGGER and record.levelno >= logging.ERROR
    ]


def test_failed_backup_logs_one_error_with_environment(settings, caplog):
    settings.DB_BACKUP_ENABLED = True
    settings.DB_BACKUP_ENVIRONMENT = "production"

    with patch("lacos.common.db_backup_tasks.DatabaseBackupService") as service_cls:
        service_cls.return_value.run.return_value = {
            "success": False,
            "error": "backup_command_failed",
        }
        runner = getattr(backup_database_to_s3, "call_local", backup_database_to_s3)
        with caplog.at_level(logging.INFO, logger=BACKUP_LOGGER):
            result = runner()

    assert result["success"] is False
    errors = _backup_errors(caplog)
    assert len(errors) == 1
    assert "environment=production" in errors[0].getMessage()
    assert "backup_command_failed" in errors[0].getMessage()


def test_backup_exception_logs_one_error_and_reraises(settings, caplog):
    settings.DB_BACKUP_ENABLED = True
    settings.DB_BACKUP_ENVIRONMENT = "production"

    with patch("lacos.common.db_backup_tasks.DatabaseBackupService") as service_cls:
        service_cls.return_value.run.side_effect = RuntimeError("docker socket gone")
        runner = getattr(backup_database_to_s3, "call_local", backup_database_to_s3)
        log_level = caplog.at_level(logging.INFO, logger=BACKUP_LOGGER)
        with log_level, pytest.raises(RuntimeError):
            runner()

    errors = _backup_errors(caplog)
    assert len(errors) == 1
    assert errors[0].exc_info is not None


def test_failed_backup_sends_one_admin_email(settings, mailoutbox):
    settings.DB_BACKUP_ENABLED = True
    settings.DB_BACKUP_ENVIRONMENT = "production"
    settings.ADMINS = [("Admin", "admin@example.org")]
    settings.DEBUG = False

    backup_logger = logging.getLogger(BACKUP_LOGGER)
    handler = AdminEmailHandler()
    handler.setLevel(logging.ERROR)
    backup_logger.addHandler(handler)
    try:
        with patch("lacos.common.db_backup_tasks.DatabaseBackupService") as service_cls:
            service_cls.return_value.run.return_value = {
                "success": False,
                "error": "upload_failed",
            }
            runner = getattr(backup_database_to_s3, "call_local", backup_database_to_s3)
            runner()
    finally:
        backup_logger.removeHandler(handler)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["admin@example.org"]
    assert "Database backup failed" in mailoutbox[0].subject
