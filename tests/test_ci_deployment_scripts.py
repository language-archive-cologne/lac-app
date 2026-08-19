# These integration tests execute only repository scripts with controlled arguments.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGURE_SSH = REPO_ROOT / "scripts" / "ci" / "configure-ssh.sh"
REMOTE_DEPLOY = REPO_ROOT / "scripts" / "ci" / "remote-deploy.sh"
REMOTE_SAML_PREFLIGHT = REPO_ROOT / "scripts" / "ci" / "remote-saml-preflight.sh"
DEPLOY = REPO_ROOT / "scripts" / "deploy" / "deploy.sh"
SSH_FILE_MODE = 0o600
PRODUCTION_RESOURCE_GROUP_JOBS = 3
NO_DEPS_COMMAND_COUNT = 4


def _run(
    script: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    command_env.update(env or {})
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=REPO_ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_configure_ssh_writes_strict_single_identity_configuration(tmp_path: Path):
    private_key = tmp_path / "source-key"
    known_hosts = tmp_path / "source-known-hosts"
    private_key.write_text("private key\n")
    known_hosts.write_text("deploy.example ssh-ed25519 AAAA\n")

    result = _run(
        CONFIGURE_SSH,
        env={
            "HOME": str(tmp_path / "home"),
            "DEPLOY_HOST": "deploy.example",
            "DEPLOY_USER": "lacos-dev-deploy",
            "SSH_PRIVATE_KEY": str(private_key),
            "SSH_KNOWN_HOSTS": str(known_hosts),
        },
    )

    assert result.returncode == 0, result.stderr
    ssh_dir = tmp_path / "home" / ".ssh"
    config = (ssh_dir / "config").read_text()
    assert "Host lac-deployment" in config
    assert "HostName deploy.example" in config
    assert "User lacos-dev-deploy" in config
    assert "BatchMode yes" in config
    assert "IdentitiesOnly yes" in config
    assert "IdentityAgent none" in config
    assert "StrictHostKeyChecking yes" in config
    assert f"UserKnownHostsFile {ssh_dir / 'known_hosts'}" in config
    assert stat.S_IMODE((ssh_dir / "deploy_key").stat().st_mode) == SSH_FILE_MODE
    assert stat.S_IMODE((ssh_dir / "known_hosts").stat().st_mode) == SSH_FILE_MODE


@pytest.mark.parametrize("missing_variable", ["SSH_PRIVATE_KEY", "SSH_KNOWN_HOSTS"])
def test_configure_ssh_rejects_missing_file_variables(
    tmp_path: Path,
    missing_variable: str,
):
    private_key = tmp_path / "source-key"
    known_hosts = tmp_path / "source-known-hosts"
    private_key.write_text("private key\n")
    known_hosts.write_text("deploy.example ssh-ed25519 AAAA\n")
    env = {
        "HOME": str(tmp_path / "home"),
        "DEPLOY_HOST": "deploy.example",
        "DEPLOY_USER": "lacos-dev-deploy",
        "SSH_PRIVATE_KEY": str(private_key),
        "SSH_KNOWN_HOSTS": str(known_hosts),
    }
    del env[missing_variable]

    result = _run(CONFIGURE_SSH, env=env)

    assert result.returncode != 0
    assert missing_variable in result.stderr


def test_remote_deploy_maps_development_to_its_dedicated_account(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    theme_artifact = tmp_path / "output.css"
    theme_artifact.write_text("compiled theme\n")
    ssh_log = tmp_path / "ssh.log"
    scp_log = tmp_path / "scp.log"
    stdin_log = tmp_path / "stdin.log"
    fake_ssh = fake_bin / "ssh"
    fake_scp = fake_bin / "scp"
    fake_ssh.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$SSH_LOG"\ncat > "$STDIN_LOG"\n',
    )
    fake_scp.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" > "$SCP_LOG"\n')
    fake_ssh.chmod(0o755)
    fake_scp.chmod(0o755)

    commit = "a" * 40
    result = _run(
        REMOTE_DEPLOY,
        "development",
        "fast",
        commit,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "DEPLOY_USER": "lacos-dev-deploy",
            "THEME_ARTIFACT_FILE": str(theme_artifact),
            "SCP_LOG": str(scp_log),
            "SSH_LOG": str(ssh_log),
            "STDIN_LOG": str(stdin_log),
        },
    )

    assert result.returncode == 0, result.stderr
    invocation = ssh_log.read_text()
    assert "-F" in invocation
    assert "lacos-dev-deploy" in invocation
    assert "/opt/lacos/lac-app" in invocation
    assert "docker-compose.dev.yml" in invocation
    assert " dev " in f" {invocation} "
    assert commit in invocation
    assert " fast " in f" {invocation} "
    assert "set -euo pipefail" in stdin_log.read_text()
    upload = scp_log.read_text()
    assert str(theme_artifact) in upload
    assert f".theme-output.{commit}.css" in upload


def test_remote_deploy_rejects_an_account_for_the_wrong_environment(tmp_path: Path):
    result = _run(
        REMOTE_DEPLOY,
        "production",
        "full",
        "a" * 40,
        env={
            "HOME": str(tmp_path / "home"),
            "DEPLOY_USER": "lacos-dev-deploy",
        },
    )

    assert result.returncode != 0
    assert "lacos-prod-deploy" in result.stderr


def test_remote_deploy_rejects_a_missing_theme_artifact(tmp_path: Path):
    missing_artifact = tmp_path / "missing.css"

    result = _run(
        REMOTE_DEPLOY,
        "development",
        "fast",
        "a" * 40,
        env={
            "HOME": str(tmp_path / "home"),
            "DEPLOY_USER": "lacos-dev-deploy",
            "THEME_ARTIFACT_FILE": str(missing_artifact),
        },
    )

    assert result.returncode != 0
    assert "theme artifact is missing or empty" in result.stderr.lower()


def test_remote_saml_preflight_uses_the_production_checkout_and_account(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    ssh_log = tmp_path / "ssh.log"
    stdin_log = tmp_path / "stdin.log"
    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" > "$SSH_LOG"\ncat > "$STDIN_LOG"\n',
    )
    fake_ssh.chmod(0o755)

    commit = "b" * 40
    result = _run(
        REMOTE_SAML_PREFLIGHT,
        commit,
        env={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "HOME": str(tmp_path / "home"),
            "DEPLOY_USER": "lacos-prod-deploy",
            "SSH_LOG": str(ssh_log),
            "STDIN_LOG": str(stdin_log),
        },
    )

    assert result.returncode == 0, result.stderr
    invocation = ssh_log.read_text()
    assert "/opt/lacos/lac-app-production" in invocation
    assert " main " in f" {invocation} "
    assert commit in invocation
    assert "lacos-prod-deploy" in invocation
    assert "worktree add --detach" in stdin_log.read_text()


def test_gitlab_pipeline_uses_hardened_serialized_commit_deployments():
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    assert "StrictHostKeyChecking=no" not in pipeline
    assert "ssh-agent" not in pipeline
    assert "scripts/ci/configure-ssh.sh" in pipeline
    assert 'scripts/ci/remote-deploy.sh development full "$CI_COMMIT_SHA"' in pipeline
    assert 'scripts/ci/remote-deploy.sh production full "$CI_COMMIT_SHA"' in pipeline
    assert "resource_group: lacos-development" in pipeline
    assert (
        pipeline.count("resource_group: lacos-production")
        >= PRODUCTION_RESOURCE_GROUP_JOBS
    )
    assert "git reset --hard origin/" not in pipeline


def test_deploy_refreshes_explorer_facets_after_django_is_ready():
    deploy = DEPLOY.read_text()
    index_command = (
        "python manage.py refresh_discovery_search --if-enabled --force"
    )
    warm_command = "python manage.py warm_explorer_facets --refresh"

    assert index_command in deploy
    assert warm_command in deploy
    assert deploy.index(index_command) < deploy.index(warm_command)
    assert deploy.index(warm_command) > deploy.index("--wait-timeout 120")


def test_deploy_does_not_warm_admission_gated_search_pages():
    deploy = DEPLOY.read_text()
    page_command = "python /app/scripts/deploy/warm_pages.py"

    assert page_command not in deploy


def test_full_deploy_does_not_build_or_recreate_dependencies():
    deploy = DEPLOY.read_text()

    assert 'docker compose -f "${compose_file}" build django huey' in deploy
    assert deploy.count("--no-deps") >= NO_DEPS_COMMAND_COUNT


def test_deploy_ensures_the_cache_service_exists_before_django():
    deploy = DEPLOY.read_text()
    cache_command = 'log "Ensuring the bounded Django cache is available"'

    assert cache_command in deploy
    assert deploy.index(cache_command) < deploy.index('if [[ "${mode}" == "full" ]]')


def test_production_deploy_controls_the_dedicated_search_service():
    deploy = DEPLOY.read_text()

    assert "web_services=(django)" in deploy
    assert 'if [[ "${branch}" == "main" ]]' in deploy
    assert "web_services+=(search)" in deploy
    assert '"${web_services[@]}"' in deploy


@pytest.mark.parametrize(
    ("compose_file", "healthcheck_host"),
    [
        ("docker-compose.dev.yml", "dev.lacos.uni-koeln.de"),
        ("docker-compose.production.yml", "lacos.uni-koeln.de"),
    ],
)
def test_django_container_uses_http_readiness_check(compose_file, healthcheck_host):
    compose = (REPO_ROOT / compose_file).read_text()

    assert "http://127.0.0.1:8000/health/ready/" in compose
    assert f'DJANGO_HEALTHCHECK_HOST: "{healthcheck_host}"' in compose
