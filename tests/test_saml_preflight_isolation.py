# These integration tests execute only trusted local tools and repository scripts.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "saml-preflight.sh"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_saml_preflight_uses_and_removes_an_isolated_worktree(tmp_path: Path):
    remote = tmp_path / "remote.git"
    source = tmp_path / "source"
    deployment = tmp_path / "lac-app-production"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "init", "-b", "main", str(source)],
        check=True,
        capture_output=True,
    )
    _git("config", "user.name", "CI Test", cwd=source)
    _git("config", "user.email", "ci@example.test", cwd=source)
    (source / "live-file.txt").write_text("original\n")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "initial", cwd=source)
    first_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("remote", "add", "origin", str(remote), cwd=source)
    _git("push", "-u", "origin", "main", cwd=source)
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(deployment)],
        check=True,
        capture_output=True,
    )
    (deployment / ".envs").mkdir()
    (deployment / ".env").write_text("DEPLOYMENT_SECRET=preserved\n")

    generator = source / "fake-saml-generator.sh"
    generator.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test -L .envs\n"
        "test -L .env\n"
        'test "$(cat live-file.txt)" = changed\n'
        'mkdir -p "$SAML_PREFLIGHT_WORK_DIR"\n'
        "printf '<EntityDescriptor />\\n' > "
        '"$SAML_PREFLIGHT_WORK_DIR/metadata.xml"\n',
    )
    generator.chmod(0o755)
    (source / "live-file.txt").write_text("changed\n")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "preflight target", cwd=source)
    target_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("push", "origin", "main", cwd=source)

    env = os.environ.copy()
    env["SAML_PREFLIGHT_GENERATOR"] = "./fake-saml-generator.sh"
    result = subprocess.run(
        [
            "bash",
            str(PREFLIGHT_SCRIPT),
            str(deployment),
            "main",
            target_commit,
            subprocess.run(
                ["id", "-un"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "<EntityDescriptor />\n"
    assert _git("rev-parse", "HEAD", cwd=deployment) == first_commit
    assert (deployment / "live-file.txt").read_text() == "original\n"
    assert not list((deployment / ".tmp").glob("saml-preflight-worktree.*"))
    worktree_count = _git(
        "worktree",
        "list",
        "--porcelain",
        cwd=deployment,
    ).count("worktree ")
    assert worktree_count == 1


def test_saml_preflight_rejects_a_stale_pipeline_without_touching_checkout(
    tmp_path: Path,
):
    deployment = tmp_path / "deployment"
    subprocess.run(
        ["git", "init", "-b", "main", str(deployment)],
        check=True,
        capture_output=True,
    )
    _git("config", "user.name", "CI Test", cwd=deployment)
    _git("config", "user.email", "ci@example.test", cwd=deployment)
    (deployment / "file.txt").write_text("one\n")
    _git("add", ".", cwd=deployment)
    _git("commit", "-m", "initial", cwd=deployment)
    commit = _git("rev-parse", "HEAD", cwd=deployment)
    _git("remote", "add", "origin", str(deployment), cwd=deployment)

    result = subprocess.run(
        [
            "bash",
            str(PREFLIGHT_SCRIPT),
            str(deployment),
            "main",
            "a" * 40,
            subprocess.run(
                ["id", "-un"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "no longer the head" in result.stderr
    assert _git("rev-parse", "HEAD", cwd=deployment) == commit
