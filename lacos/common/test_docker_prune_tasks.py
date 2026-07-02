from __future__ import annotations

from unittest.mock import patch

from lacos.common.docker_prune_tasks import prune_docker_resources


def _call(task_fn):
    return getattr(task_fn, "call_local", task_fn)()


def test_manual_prune_runs_service_forced_when_enabled(settings):
    settings.DOCKER_PRUNE_ENABLED = True

    with patch("lacos.common.docker_prune_tasks.DockerPruneService") as service_cls:
        service_cls.return_value.run.return_value = {"success": True, "freed_percent": 12.0}
        result = _call(prune_docker_resources)

    assert result["success"] is True
    service_cls.return_value.run.assert_called_once_with(force=True)


def test_prune_skips_when_disabled(settings):
    settings.DOCKER_PRUNE_ENABLED = False

    with patch("lacos.common.docker_prune_tasks.DockerPruneService") as service_cls:
        result = _call(prune_docker_resources)

    assert result == {"success": False, "skipped": "docker_prune_disabled"}
    service_cls.assert_not_called()
