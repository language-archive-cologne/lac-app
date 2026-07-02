from __future__ import annotations

from collections import namedtuple
from subprocess import CalledProcessError
from unittest.mock import MagicMock

from lacos.common.services.docker_prune_service import DockerPruneService

Usage = namedtuple("Usage", ["total", "used", "free"])


def _usage(percent: int) -> Usage:
    total = 100
    return Usage(total=total, used=percent, free=total - percent)


def test_prunes_when_above_threshold(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    settings.DOCKER_PRUNE_PATH = "/"
    runner = MagicMock()
    disk = MagicMock(side_effect=[_usage(90), _usage(50)])  # before, after
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run()

    assert result["success"] is True
    assert result["freed_percent"] == 40.0
    assert runner.call_count == 3  # container, image, builder prune


def test_skips_below_threshold(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    runner = MagicMock()
    disk = MagicMock(return_value=_usage(50))
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run()

    assert result["skipped"] == "below_threshold"
    assert result["used_percent"] == 50.0
    runner.assert_not_called()


def test_force_prunes_below_threshold(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    runner = MagicMock()
    disk = MagicMock(side_effect=[_usage(20), _usage(15)])
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run(force=True)

    assert result["success"] is True
    assert runner.call_count == 3


def test_reports_error_when_prune_command_fails(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    runner = MagicMock(side_effect=CalledProcessError(1, "docker", stderr="boom"))
    disk = MagicMock(return_value=_usage(95))
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run()

    assert result["success"] is False
    assert "prune_failed" in result["error"]
    assert result["stderr"] == "boom"


def test_prune_succeeds_even_if_post_measurement_fails(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    runner = MagicMock()
    # first read OK (90%), second read (after prune) raises
    disk = MagicMock(side_effect=[_usage(90), OSError("gone")])
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run()

    assert result["success"] is True
    assert result["used_percent_before"] == 90.0
    assert "freed_percent" not in result
    assert runner.call_count == 3


def test_reports_error_when_docker_binary_missing(settings):
    settings.DOCKER_PRUNE_THRESHOLD_PERCENT = 80
    runner = MagicMock(side_effect=FileNotFoundError("no docker"))
    disk = MagicMock(return_value=_usage(95))
    service = DockerPruneService(command_runner=runner, disk_usage_fn=disk)

    result = service.run()

    assert result["success"] is False
    assert "docker_not_found" in result["error"]
