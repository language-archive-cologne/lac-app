# These integration tests execute only trusted local tools and repository scripts.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "saml-preflight.sh"
PRODUCTION_ENV_FILES = (".django", ".postgres", ".storage")
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _current_user() -> str:
    return subprocess.run(
        ["id", "-un"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _create_preflight_repositories(
    tmp_path: Path,
) -> tuple[Path, Path, str]:
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
    local_envs = source / ".envs" / ".local"
    local_envs.mkdir(parents=True)
    (local_envs / ".django").write_text("LOCAL_ONLY=true\n")
    (source / "live-file.txt").write_text("original\n")
    _git("add", ".envs/.local/.django", "live-file.txt", cwd=source)
    _git("commit", "-m", "initial", cwd=source)
    first_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("remote", "add", "origin", str(remote), cwd=source)
    _git("push", "-u", "origin", "main", cwd=source)
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(deployment)],
        check=True,
        capture_output=True,
    )
    (deployment / ".env").write_text("DEPLOYMENT_SECRET=preserved\n")
    return source, deployment, first_commit


def _push_preflight_target(source: Path, generator_body: str) -> str:
    generator = source / "fake-saml-generator.sh"
    generator.write_text(generator_body)
    generator.chmod(0o755)
    (source / "live-file.txt").write_text("changed\n")
    _git("add", "fake-saml-generator.sh", "live-file.txt", cwd=source)
    _git("commit", "-m", "preflight target", cwd=source)
    target_commit = _git("rev-parse", "HEAD", cwd=source)
    _git("push", "origin", "main", cwd=source)
    return target_commit


def _run_preflight(
    deployment: Path,
    target_commit: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SAML_PREFLIGHT_GENERATOR"] = "./fake-saml-generator.sh"
    return subprocess.run(
        [
            "bash",
            str(PREFLIGHT_SCRIPT),
            str(deployment),
            "main",
            target_commit,
            _current_user(),
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_saml_preflight_uses_and_removes_an_isolated_worktree(tmp_path: Path):
    source, deployment, first_commit = _create_preflight_repositories(tmp_path)
    production_envs = deployment / ".envs" / ".production"
    production_envs.mkdir()
    production_envs.chmod(PRIVATE_DIRECTORY_MODE)
    for filename in PRODUCTION_ENV_FILES:
        env_file = production_envs / filename
        env_file.write_text(f"SOURCE={filename}\n")
        env_file.chmod(PRIVATE_FILE_MODE)

    target_commit = _push_preflight_target(
        source,
        "#!/bin/sh\n"
        "set -eu\n"
        "test -d .envs\n"
        "test ! -L .envs\n"
        "test -d .envs/.production\n"
        "test ! -L .envs/.production\n"
        "test -L .envs/.production/.django\n"
        "test -L .envs/.production/.postgres\n"
        "test -L .envs/.production/.storage\n"
        "test ! -e .envs/.envs\n"
        'test "$(cat .envs/.production/.django)" = "SOURCE=.django"\n'
        'test "$(cat .envs/.production/.postgres)" = "SOURCE=.postgres"\n'
        'test "$(cat .envs/.production/.storage)" = "SOURCE=.storage"\n'
        "test -L .env\n"
        'test "$SAML_PREFLIGHT_ROOT_GENERATOR" = 1\n'
        'test "$SAML_SP_KEY_FILE" = /etc/shibboleth/prod-sp-key.pem\n'
        'test "$SAML_SP_CERT_FILE" = /etc/shibboleth/prod-sp-cert.pem\n'
        'test -z "${SAML_PREFLIGHT_SP_KEY_FILE:-}"\n'
        'test -z "${SAML_PREFLIGHT_SP_CERT_FILE:-}"\n'
        'test "$SAML_PREFLIGHT_REPO_ROOT" = "$PWD"\n'
        'test "$SAML_PREFLIGHT_BASE_URL" = https://lac.uni-koeln.de\n'
        'test "$(cat live-file.txt)" = changed\n'
        'mkdir -p "$SAML_PREFLIGHT_WORK_DIR"\n'
        "printf '<EntityDescriptor />\\n' > "
        '"$SAML_PREFLIGHT_WORK_DIR/metadata.xml"\n',
    )
    result = _run_preflight(deployment, target_commit)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "<EntityDescriptor />\n"
    assert _git("rev-parse", "HEAD", cwd=deployment) == first_commit
    assert (deployment / "live-file.txt").read_text() == "original\n"
    assert (
        stat.S_IMODE((deployment / ".worktrees").stat().st_mode)
        == PRIVATE_DIRECTORY_MODE
    )
    assert not list((deployment / ".tmp").glob("saml-preflight-worktree.*"))
    worktree_count = _git(
        "worktree",
        "list",
        "--porcelain",
        cwd=deployment,
    ).count("worktree ")
    assert worktree_count == 1


def test_saml_preflight_rejects_missing_production_environment_file(
    tmp_path: Path,
):
    source, deployment, first_commit = _create_preflight_repositories(tmp_path)
    production_envs = deployment / ".envs" / ".production"
    production_envs.mkdir()
    production_envs.chmod(PRIVATE_DIRECTORY_MODE)
    for filename in (".django", ".postgres"):
        env_file = production_envs / filename
        env_file.write_text(f"SOURCE={filename}\n")
        env_file.chmod(PRIVATE_FILE_MODE)
    target_commit = _push_preflight_target(source, "#!/bin/sh\nexit 99\n")

    result = _run_preflight(deployment, target_commit)

    assert result.returncode != 0
    assert "production environment file is missing" in result.stderr.lower()
    assert ".storage" in result.stderr
    assert _git("rev-parse", "HEAD", cwd=deployment) == first_commit
    assert (
        _git("worktree", "list", "--porcelain", cwd=deployment).count("worktree ")
        == 1
    )


def test_saml_preflight_rejects_overly_permissive_production_secrets(
    tmp_path: Path,
):
    source, deployment, first_commit = _create_preflight_repositories(tmp_path)
    production_envs = deployment / ".envs" / ".production"
    production_envs.mkdir()
    production_envs.chmod(PRIVATE_DIRECTORY_MODE)
    for filename in PRODUCTION_ENV_FILES:
        env_file = production_envs / filename
        env_file.write_text(f"SOURCE={filename}\n")
        env_file.chmod(PRIVATE_FILE_MODE)
    (production_envs / ".storage").chmod(0o640)
    target_commit = _push_preflight_target(source, "#!/bin/sh\nexit 99\n")

    result = _run_preflight(deployment, target_commit)

    assert result.returncode != 0
    assert "must not grant group or other permissions" in result.stderr.lower()
    assert ".storage" in result.stderr
    assert _git("rev-parse", "HEAD", cwd=deployment) == first_commit


def test_saml_preflight_rejects_a_symlinked_production_environment(
    tmp_path: Path,
):
    source, deployment, first_commit = _create_preflight_repositories(tmp_path)
    external_envs = tmp_path / "external-production-envs"
    external_envs.mkdir()
    for filename in PRODUCTION_ENV_FILES:
        (external_envs / filename).write_text(f"SOURCE={filename}\n")
    (deployment / ".envs" / ".production").symlink_to(
        external_envs,
        target_is_directory=True,
    )
    target_commit = _push_preflight_target(source, "#!/bin/sh\nexit 99\n")

    result = _run_preflight(deployment, target_commit)

    assert result.returncode != 0
    assert "must not be a symlink" in result.stderr.lower()
    assert _git("rev-parse", "HEAD", cwd=deployment) == first_commit


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
