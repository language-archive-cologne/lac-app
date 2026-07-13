# These integration tests execute only trusted local tools and repository scripts.
# ruff: noqa: S603, S607

from __future__ import annotations

import fcntl
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "deploy.sh"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def deployment_repo(tmp_path: Path) -> dict[str, Path | str]:
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    deployment = tmp_path / "deployment"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "init", "-b", "dev", str(source)],
        check=True,
        capture_output=True,
    )
    _git("config", "user.name", "CI Test", cwd=source)
    _git("config", "user.email", "ci@example.test", cwd=source)
    (source / "docker-compose.dev.yml").write_text("services: {}\n")
    (source / "version.txt").write_text("one\n")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "initial", cwd=source)
    first_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("remote", "add", "origin", str(remote), cwd=source)
    _git("push", "-u", "origin", "dev", cwd=source)
    subprocess.run(
        ["git", "clone", "--branch", "dev", str(remote), str(deployment)],
        check=True,
        capture_output=True,
    )

    (source / "version.txt").write_text("two\n")
    _git("add", "version.txt", cwd=source)
    _git("commit", "-m", "second", cwd=source)
    second_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("push", "origin", "dev", cwd=source)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n')
    fake_docker.chmod(0o755)
    docker_socket = tmp_path / "docker.sock"
    docker_socket.touch()

    return {
        "deployment": deployment,
        "docker_log": docker_log,
        "docker_socket": docker_socket,
        "fake_bin": fake_bin,
        "first_commit": first_commit,
        "second_commit": second_commit,
        "source": source,
    }


def _deploy(
    repo: dict[str, Path | str],
    commit: str,
    mode: str = "full",
    expected_user: str | None = None,
) -> subprocess.CompletedProcess[str]:
    deployment = Path(repo["deployment"])
    current_user = subprocess.run(
        ["id", "-un"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{repo['fake_bin']}:{env['PATH']}",
            "DOCKER_LOG": str(repo["docker_log"]),
            "DOCKER_SOCKET": str(repo["docker_socket"]),
        },
    )
    return subprocess.run(
        [
            "bash",
            str(DEPLOY_SCRIPT),
            str(deployment),
            "docker-compose.dev.yml",
            "dev",
            commit,
            mode,
            expected_user or current_user,
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_full_deploy_resets_to_the_exact_pipeline_commit(deployment_repo):
    result = _deploy(deployment_repo, str(deployment_repo["second_commit"]))

    assert result.returncode == 0, result.stderr
    deployment = Path(deployment_repo["deployment"])
    assert _git("rev-parse", "HEAD", cwd=deployment) == deployment_repo["second_commit"]
    assert (deployment / "version.txt").read_text() == "two\n"
    commands = Path(deployment_repo["docker_log"]).read_text().splitlines()
    assert commands == [
        "compose -f docker-compose.dev.yml --profile build run --rm --no-deps theme",
        "compose -f docker-compose.dev.yml up -d --build --force-recreate huey django",
    ]


def test_fast_deploy_preserves_the_controlled_restart_order(deployment_repo):
    result = _deploy(
        deployment_repo,
        str(deployment_repo["second_commit"]),
        mode="fast",
    )

    assert result.returncode == 0, result.stderr
    commands = Path(deployment_repo["docker_log"]).read_text().splitlines()
    assert commands == [
        "compose -f docker-compose.dev.yml --profile build run --rm --no-deps theme",
        "compose -f docker-compose.dev.yml stop -t 30 huey",
        "compose -f docker-compose.dev.yml up -d --no-build huey",
        "compose -f docker-compose.dev.yml restart django",
    ]


@pytest.mark.parametrize("commit", ["abc", "A" * 40, "g" * 40, "a" * 39])
def test_deploy_rejects_invalid_commit_identifiers(deployment_repo, commit: str):
    result = _deploy(deployment_repo, commit)

    assert result.returncode != 0
    assert "40 character lowercase commit SHA" in result.stderr
    assert not Path(deployment_repo["docker_log"]).exists()


def test_deploy_rejects_a_stale_pipeline_commit(deployment_repo):
    result = _deploy(deployment_repo, str(deployment_repo["first_commit"]))

    assert result.returncode != 0
    assert "no longer the head" in result.stderr
    deployment = Path(deployment_repo["deployment"])
    assert _git("rev-parse", "HEAD", cwd=deployment) == deployment_repo["first_commit"]
    assert not Path(deployment_repo["docker_log"]).exists()


def test_deploy_rejects_the_wrong_remote_account(deployment_repo):
    result = _deploy(
        deployment_repo,
        str(deployment_repo["second_commit"]),
        expected_user="somebody-else",
    )

    assert result.returncode != 0
    assert "must run as somebody-else" in result.stderr
    assert not Path(deployment_repo["docker_log"]).exists()


def test_deploy_fails_when_the_vm_lock_is_already_held(deployment_repo):
    lock_path = Path(deployment_repo["deployment"]) / ".deploy.lock"
    lock_path.touch()
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = _deploy(deployment_repo, str(deployment_repo["second_commit"]))

    assert result.returncode != 0
    assert "deployment is already in progress" in result.stderr
    assert not Path(deployment_repo["docker_log"]).exists()
