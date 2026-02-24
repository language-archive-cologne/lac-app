from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from subprocess import CompletedProcess
from typing import Callable
from typing import Sequence

import boto3
from botocore.config import Config
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class DatabaseBackupService:
    """Create DB dumps via cookiecutter command, upload to S3, and prune retention."""

    def __init__(
        self,
        *,
        s3_client=None,
        command_runner: CommandRunner | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.compose_file = str(getattr(settings, "DB_BACKUP_COMPOSE_FILE", "docker-compose.dev.yml"))
        self.compose_project_dir = Path(getattr(settings, "DB_BACKUP_COMPOSE_PROJECT_DIR", settings.BASE_DIR))
        self.compose_project_name = str(getattr(settings, "DB_BACKUP_COMPOSE_PROJECT_NAME", "")).strip()
        self.backup_dir = Path(getattr(settings, "DB_BACKUP_BACKUP_DIR", "/backups"))
        self.bucket_name = str(getattr(settings, "DB_BACKUP_S3_BUCKET", "backups"))
        self.s3_prefix = str(getattr(settings, "DB_BACKUP_S3_PREFIX", ""))
        self.retention_days = int(getattr(settings, "DB_BACKUP_RETENTION_DAYS", 7))
        self.docker_api_version = str(getattr(settings, "DB_BACKUP_DOCKER_API_VERSION", "")).strip()

        self.command_runner = command_runner or subprocess.run
        self.now_fn = now_fn or timezone.now
        self.s3_client = s3_client or self._build_s3_client()

    def run(self) -> dict:
        """Run full workflow: backup, upload, local cleanup, and S3 retention cleanup."""
        command_result = self._run_backup_command()
        if command_result.returncode != 0:
            logger.error(
                "Database backup command failed with return code %s: %s",
                command_result.returncode,
                command_result.stderr.strip(),
            )
            return {
                "success": False,
                "error": "backup_command_failed",
                "returncode": command_result.returncode,
                "stderr": command_result.stderr.strip(),
            }

        backup_file = self._latest_local_backup()
        if backup_file is None:
            return {
                "success": False,
                "error": "backup_not_found",
                "detail": f"No backup_*.sql.gz found in {self.backup_dir}",
            }

        s3_key = self._build_s3_key(backup_file.name)
        self.s3_client.upload_file(str(backup_file), self.bucket_name, s3_key)
        logger.info("Uploaded backup file %s to s3://%s/%s", backup_file.name, self.bucket_name, s3_key)

        local_removed = self._remove_local_backups()
        remote_removed = self._remove_old_remote_backups()

        return {
            "success": True,
            "backup_file": backup_file.name,
            "bucket": self.bucket_name,
            "key": s3_key,
            "local_removed": local_removed,
            "remote_removed": remote_removed,
        }

    def _run_backup_command(self) -> subprocess.CompletedProcess[str]:
        command = self._backup_command()
        result = self._run_command(command, "primary compose")

        if result.returncode == 0:
            return result

        if not self._is_compose_tooling_error(result):
            return result

        legacy_result = self._run_command(self._legacy_backup_command(), "legacy compose")
        if legacy_result.returncode == 0:
            return legacy_result
        if self._docker_cli_missing(result, legacy_result):
            return CompletedProcess(
                self._legacy_backup_command(),
                127,
                stdout="",
                stderr="Command not found: docker and docker-compose",
            )
        if not self._should_try_exec_fallback(legacy_result):
            return legacy_result

        exec_result = self._run_command(self._exec_backup_command(), "docker exec fallback")
        return exec_result

    def _backup_command(self) -> Sequence[str]:
        command = [
            "docker",
            "compose",
        ]
        if self.compose_project_name:
            command.extend(["-p", self.compose_project_name])

        command.extend(
            [
                "-f",
                self.compose_file,
                "run",
                "--rm",
                "postgres",
                "backup",
            ]
        )
        return command

    def _legacy_backup_command(self) -> Sequence[str]:
        command = ["docker-compose"]
        if self.compose_project_name:
            command.extend(["-p", self.compose_project_name])
        command.extend(["-f", self.compose_file, "run", "--rm", "postgres", "backup"])
        return command

    def _exec_backup_command(self) -> Sequence[str]:
        container_name = self._find_postgres_container_name()
        if not container_name:
            return ["false"]
        return ["docker", "exec", container_name, "backup"]

    def _find_postgres_container_name(self) -> str | None:
        command = [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.service=postgres",
        ]
        if self.compose_project_name:
            command.extend(
                [
                    "--filter",
                    f"label=com.docker.compose.project={self.compose_project_name}",
                ]
            )
        command.extend(["--format", "{{.Names}}"])

        result = self._run_command(command, "find postgres container")
        if result.returncode != 0:
            logger.error("Failed to identify postgres container for backup fallback: %s", result.stderr.strip())
            return None

        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not names:
            logger.error("No running postgres container found for backup fallback.")
            return None
        return names[0]

    def _run_command(self, command: Sequence[str], label: str) -> CompletedProcess[str]:
        logger.info("Trying %s: %s", label, " ".join(command))
        env_vars = os.environ.copy()
        if self.docker_api_version:
            env_vars["DOCKER_API_VERSION"] = self.docker_api_version

        try:
            result = self.command_runner(
                command,
                cwd=str(self.compose_project_dir),
                capture_output=True,
                text=True,
                check=False,
                env=env_vars,
            )
        except FileNotFoundError:
            missing_binary = command[0] if command else "unknown"
            stderr = f"Command not found: {missing_binary}"
            result = CompletedProcess(command, 127, stdout="", stderr=stderr)
            logger.warning("%s unavailable: %s", label, stderr)

        retry_api_version = self._extract_minimum_docker_api_version(result.stderr)
        if (
            retry_api_version
            and command
            and command[0] in {"docker", "docker-compose"}
            and env_vars.get("DOCKER_API_VERSION") != retry_api_version
        ):
            retry_env = env_vars.copy()
            retry_env["DOCKER_API_VERSION"] = retry_api_version
            logger.info(
                "Retrying %s with DOCKER_API_VERSION=%s due to client/server API mismatch.",
                label,
                retry_api_version,
            )
            result = self.command_runner(
                command,
                cwd=str(self.compose_project_dir),
                capture_output=True,
                text=True,
                check=False,
                env=retry_env,
            )

        if result.returncode != 0:
            logger.warning("%s failed with code %s: %s", label, result.returncode, result.stderr.strip())
        return result

    def _is_compose_tooling_error(self, result: CompletedProcess[str]) -> bool:
        stderr = (result.stderr or "").lower()
        return any(
            marker in stderr
            for marker in (
                "not a docker command",
                "unknown command \"compose\"",
                "unknown shorthand flag: 'f' in -f",
                "unknown shorthand flag: 'p' in -p",
                "client version",
                "command not found",
            )
        )

    def _should_try_exec_fallback(self, result: CompletedProcess[str]) -> bool:
        if self._is_compose_tooling_error(result):
            return True
        stderr = (result.stderr or "").lower()
        return any(
            marker in stderr
            for marker in (
                "could not translate host name",
                "name or service not known",
                "temporary failure in name resolution",
                "no such host",
            )
        )

    def _docker_cli_missing(
        self,
        primary_result: CompletedProcess[str],
        legacy_result: CompletedProcess[str],
    ) -> bool:
        primary_stderr = (primary_result.stderr or "").lower()
        legacy_stderr = (legacy_result.stderr or "").lower()
        return "command not found: docker" in primary_stderr and "command not found: docker-compose" in legacy_stderr

    def _extract_minimum_docker_api_version(self, stderr: str) -> str | None:
        if not stderr:
            return None
        match = re.search(r"minimum supported api version is ([0-9.]+)", stderr, re.IGNORECASE)
        if not match:
            return None
        return match.group(1)

    def _latest_local_backup(self) -> Path | None:
        matches = sorted(
            self.backup_dir.glob("backup_*.sql.gz"),
            key=lambda file_path: file_path.stat().st_mtime,
            reverse=True,
        )
        if not matches:
            logger.error("No local backup files found in %s after backup command.", self.backup_dir)
            return None
        return matches[0]

    def _remove_local_backups(self) -> int:
        removed = 0
        for backup_file in self.backup_dir.glob("backup_*.sql.gz"):
            try:
                backup_file.unlink(missing_ok=True)
                removed += 1
            except OSError as exc:
                logger.warning("Could not remove local backup file %s: %s", backup_file, exc)
        logger.info("Removed %s local backup files from %s", removed, self.backup_dir)
        return removed

    def _remove_old_remote_backups(self) -> int:
        removed = 0
        cutoff = self.now_fn() - timedelta(days=self.retention_days)

        paginator = self.s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self._prefix_with_slash()):
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                if not self._is_backup_key(key):
                    continue

                last_modified = item.get("LastModified")
                if last_modified and last_modified < cutoff:
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
                    removed += 1

        logger.info("Removed %s remote backup files older than %s days.", removed, self.retention_days)
        return removed

    def _is_backup_key(self, key: str) -> bool:
        filename = Path(key).name
        return filename.startswith("backup_") and filename.endswith(".sql.gz")

    def _prefix_with_slash(self) -> str:
        prefix = self.s3_prefix.strip("/")
        if not prefix:
            return ""
        return f"{prefix}/"

    def _build_s3_key(self, filename: str) -> str:
        prefix = self._prefix_with_slash()
        if not prefix:
            return filename
        return f"{prefix}{filename}"

    def _build_s3_client(self):
        endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
        configured_pool_size = getattr(settings, "AWS_S3_MAX_POOL_CONNECTIONS", 50)
        try:
            max_pool_connections = max(1, int(configured_pool_size))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid AWS_S3_MAX_POOL_CONNECTIONS value %r. Falling back to 50.",
                configured_pool_size,
            )
            max_pool_connections = 50
        client_kwargs = {
            "service_name": "s3",
            "region_name": getattr(settings, "AWS_S3_REGION_NAME", None),
            "aws_access_key_id": getattr(settings, "AWS_ACCESS_KEY_ID", None),
            "aws_secret_access_key": getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        }
        client_kwargs = {key: value for key, value in client_kwargs.items() if value is not None}
        config_kwargs = {
            "max_pool_connections": max_pool_connections,
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
            config_kwargs["signature_version"] = getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4")
            config_kwargs["s3"] = {"addressing_style": "path"}
        client_kwargs["config"] = Config(**config_kwargs)

        return boto3.client(**client_kwargs)
