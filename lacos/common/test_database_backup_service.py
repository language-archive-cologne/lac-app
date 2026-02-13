from __future__ import annotations

import subprocess
from datetime import timedelta
from unittest.mock import Mock

from django.utils import timezone

from lacos.common.services.database_backup_service import DatabaseBackupService


def _runner_success(command, **kwargs):
    return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")


def test_database_backup_service_uploads_and_prunes(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.dev.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")
    settings.DB_BACKUP_S3_BUCKET = "backups"
    settings.DB_BACKUP_S3_PREFIX = "db-backups"
    settings.DB_BACKUP_RETENTION_DAYS = 7

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "backup_2026_02_06T02_00_00.sql.gz"
    dump_file.write_bytes(b"dump")

    fixed_now = timezone.now()
    old_timestamp = fixed_now - timedelta(days=10)
    fresh_timestamp = fixed_now - timedelta(days=2)

    paginator = Mock()
    paginator.paginate.return_value = [
        {
            "Contents": [
                {"Key": "db-backups/backup_old.sql.gz", "LastModified": old_timestamp},
                {"Key": "db-backups/backup_recent.sql.gz", "LastModified": fresh_timestamp},
                {"Key": "db-backups/notes.txt", "LastModified": old_timestamp},
            ]
        }
    ]
    s3_client = Mock()
    s3_client.get_paginator.return_value = paginator

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_success,
        now_fn=lambda: fixed_now,
    )

    result = service.run()

    assert result["success"] is True
    assert result["backup_file"] == dump_file.name
    assert result["bucket"] == "backups"
    assert result["key"] == f"db-backups/{dump_file.name}"
    assert result["remote_removed"] == 1
    assert result["local_removed"] == 1

    s3_client.upload_file.assert_called_once_with(
        str(dump_file),
        "backups",
        f"db-backups/{dump_file.name}",
    )
    s3_client.delete_object.assert_called_once_with(
        Bucket="backups",
        Key="db-backups/backup_old.sql.gz",
    )
    assert list(backup_dir.glob("backup_*.sql.gz")) == []


def test_database_backup_service_fails_when_backup_command_fails(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.dev.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")

    s3_client = Mock()

    def _runner_fail(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="boom")

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_fail,
    )

    result = service.run()

    assert result["success"] is False
    assert result["error"] == "backup_command_failed"
    s3_client.upload_file.assert_not_called()


def test_database_backup_service_fails_when_dump_not_found(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.dev.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")

    (tmp_path / "backups").mkdir(parents=True, exist_ok=True)

    s3_client = Mock()
    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_success,
    )

    result = service.run()

    assert result["success"] is False
    assert result["error"] == "backup_not_found"
    s3_client.upload_file.assert_not_called()


def test_database_backup_service_falls_back_to_docker_compose(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.dev.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")
    settings.DB_BACKUP_S3_BUCKET = "backups"
    settings.DB_BACKUP_S3_PREFIX = "db-backups"

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "backup_2026_02_06T02_00_00.sql.gz"

    calls = []

    def _runner_with_fallback(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="docker: 'compose' is not a docker command.",
            )
        dump_file.write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": []}]
    s3_client = Mock()
    s3_client.get_paginator.return_value = paginator

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_with_fallback,
        now_fn=timezone.now,
    )

    result = service.run()

    assert result["success"] is True
    assert len(calls) == 2
    assert calls[0][:2] == ["docker", "compose"]
    assert calls[1][0] == "docker-compose"


def test_database_backup_service_falls_back_when_compose_f_flag_is_old_docker(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.dev.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_COMPOSE_PROJECT_NAME = "lac-app"
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")
    settings.DB_BACKUP_S3_BUCKET = "backups"
    settings.DB_BACKUP_S3_PREFIX = "db-backups"

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "backup_2026_02_06T02_00_00.sql.gz"

    calls = []

    def _runner_with_old_docker(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(
                command,
                125,
                stdout="",
                stderr="unknown shorthand flag: 'f' in -f",
            )
        dump_file.write_bytes(b"dump")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": []}]
    s3_client = Mock()
    s3_client.get_paginator.return_value = paginator

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_with_old_docker,
        now_fn=timezone.now,
    )

    result = service.run()

    assert result["success"] is True
    assert len(calls) == 2
    assert calls[0][:2] == ["docker", "compose"]
    assert calls[1][0] == "docker-compose"


def test_database_backup_service_falls_back_to_docker_exec(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.local.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_COMPOSE_PROJECT_NAME = "lac-app"
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")
    settings.DB_BACKUP_S3_BUCKET = "backups"
    settings.DB_BACKUP_S3_PREFIX = "db-backups"

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "backup_2026_02_06T02_00_00.sql.gz"

    calls = []

    def _runner_with_exec_fallback(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "compose"]:
            return subprocess.CompletedProcess(
                command,
                125,
                stdout="",
                stderr="unknown shorthand flag: 'p' in -p",
            )
        if command and command[0] == "docker-compose":
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="client version 1.41 is too old. Minimum supported API version is 1.44",
            )
        if command[:2] == ["docker", "ps"]:
            return subprocess.CompletedProcess(command, 0, stdout="lac-app-postgres-1\n", stderr="")
        if command[:2] == ["docker", "exec"]:
            dump_file.write_bytes(b"dump")
            return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")

    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": []}]
    s3_client = Mock()
    s3_client.get_paginator.return_value = paginator

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_with_exec_fallback,
        now_fn=timezone.now,
    )

    result = service.run()

    assert result["success"] is True
    assert any(command[:2] == ["docker", "exec"] for command in calls)


def test_database_backup_service_handles_missing_docker_cli(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.local.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_COMPOSE_PROJECT_NAME = "lac-app"
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")

    s3_client = Mock()

    def _runner_missing_cli(command, **kwargs):
        if command and command[0] in {"docker", "docker-compose"}:
            raise FileNotFoundError(command[0])
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unexpected")

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_missing_cli,
        now_fn=timezone.now,
    )

    result = service.run()

    assert result["success"] is False
    assert result["error"] == "backup_command_failed"
    assert result["returncode"] == 127
    assert result["stderr"] == "Command not found: docker and docker-compose"
    s3_client.upload_file.assert_not_called()


def test_database_backup_service_retries_with_minimum_docker_api_version(settings, tmp_path):
    settings.DB_BACKUP_COMPOSE_FILE = "docker-compose.local.yml"
    settings.DB_BACKUP_COMPOSE_PROJECT_DIR = str(tmp_path)
    settings.DB_BACKUP_COMPOSE_PROJECT_NAME = "lac-app"
    settings.DB_BACKUP_BACKUP_DIR = str(tmp_path / "backups")
    settings.DB_BACKUP_S3_BUCKET = "backups"
    settings.DB_BACKUP_S3_PREFIX = "db-backups"

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_file = backup_dir / "backup_2026_02_06T02_00_00.sql.gz"
    api_versions = []

    def _runner_with_api_retry(command, **kwargs):
        api_version = kwargs.get("env", {}).get("DOCKER_API_VERSION")
        if command[:2] == ["docker", "compose"]:
            api_versions.append(api_version)
            if api_version == "1.44":
                dump_file.write_bytes(b"dump")
                return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")
            return subprocess.CompletedProcess(
                command,
                1,
                stdout="",
                stderr="client version 1.41 is too old. Minimum supported API version is 1.44",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": []}]
    s3_client = Mock()
    s3_client.get_paginator.return_value = paginator

    service = DatabaseBackupService(
        s3_client=s3_client,
        command_runner=_runner_with_api_retry,
        now_fn=timezone.now,
    )

    result = service.run()

    assert result["success"] is True
    assert api_versions[-1] == "1.44"
    assert len(api_versions) == 2
