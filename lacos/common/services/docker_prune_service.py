from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Callable

from django.conf import settings

logger = logging.getLogger(__name__)

CommandRunner = Callable[..., subprocess.CompletedProcess]
DiskUsageFn = Callable[[str], object]


class DockerPruneService:
    """Reclaim Docker disk space when the host is under pressure.

    Removes stopped containers, dangling images, and build cache. The prune is
    threshold-gated: it only runs when the monitored path's disk usage is at or
    above ``DOCKER_PRUNE_THRESHOLD_PERCENT`` unless ``force=True``. This keeps
    build cache warm during normal operation (so full-deploy rebuilds stay fast)
    and only reclaims aggressively when space is genuinely tight.

    Designed to run from the Huey worker, which mounts the host Docker socket and
    binary in the production compose service. Collaborators are injected so the
    behaviour is fully unit-testable without touching Docker or the filesystem.
    """

    def __init__(
        self,
        *,
        command_runner: CommandRunner | None = None,
        disk_usage_fn: DiskUsageFn | None = None,
    ) -> None:
        self.path = str(getattr(settings, "DOCKER_PRUNE_PATH", "/"))
        self.threshold_percent = int(getattr(settings, "DOCKER_PRUNE_THRESHOLD_PERCENT", 80))
        self.docker_bin = str(getattr(settings, "DOCKER_PRUNE_DOCKER_BIN", "docker"))
        self.command_runner = command_runner or subprocess.run
        self.disk_usage_fn = disk_usage_fn or shutil.disk_usage

    def _used_percent(self) -> float:
        usage = self.disk_usage_fn(self.path)
        if usage.total <= 0:
            return 0.0
        return usage.used / usage.total * 100.0

    def _prune_commands(self) -> list[list[str]]:
        # Only removes unused resources; never touches running containers or
        # named volumes (no --volumes flag), so data is safe.
        return [
            [self.docker_bin, "container", "prune", "-f"],
            [self.docker_bin, "image", "prune", "-f"],
            [self.docker_bin, "builder", "prune", "-af"],
        ]

    def run(self, *, force: bool = False) -> dict:
        try:
            used_before = self._used_percent()
        except OSError as exc:
            logger.warning("DockerPruneService: could not read disk usage for %s: %s", self.path, exc)
            return {"success": False, "error": f"disk_usage_failed: {exc}"}

        if not force and used_before < self.threshold_percent:
            logger.info(
                "DockerPruneService: skipped, disk %.1f%% < threshold %d%% (path=%s)",
                used_before, self.threshold_percent, self.path,
            )
            return {
                "success": True,
                "skipped": "below_threshold",
                "used_percent": round(used_before, 1),
                "threshold_percent": self.threshold_percent,
            }

        commands_run: list[str] = []
        for cmd in self._prune_commands():
            try:
                self.command_runner(cmd, check=True, capture_output=True, text=True)
                commands_run.append(" ".join(cmd))
            except FileNotFoundError as exc:
                logger.error("DockerPruneService: docker binary not found (%s): %s", self.docker_bin, exc)
                return {"success": False, "error": f"docker_not_found: {exc}", "commands_run": commands_run}
            except subprocess.CalledProcessError as exc:
                logger.error("DockerPruneService: command failed %s: %s", cmd, exc.stderr or exc)
                return {
                    "success": False,
                    "error": f"prune_failed: {' '.join(cmd)}",
                    "stderr": (exc.stderr or "").strip()[:500],
                    "commands_run": commands_run,
                }

        # Best-effort post-measurement: the prune already succeeded, so a
        # transient disk-usage read error must not fail the whole task.
        try:
            used_after = self._used_percent()
        except OSError as exc:
            logger.warning("DockerPruneService: could not read disk usage after prune: %s", exc)
            return {
                "success": True,
                "used_percent_before": round(used_before, 1),
                "commands_run": commands_run,
            }

        logger.info(
            "DockerPruneService: pruned, disk %.1f%% -> %.1f%% (path=%s)",
            used_before, used_after, self.path,
        )
        return {
            "success": True,
            "used_percent_before": round(used_before, 1),
            "used_percent_after": round(used_after, 1),
            "freed_percent": round(used_before - used_after, 1),
            "commands_run": commands_run,
        }
