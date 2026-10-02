# These integration tests execute only repository scripts with controlled arguments.
# ruff: noqa: S603, S607

from __future__ import annotations

import contextlib
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
DEV_PUBLIC_INDEX_CONSUMERS = 2
VALIDATION_JOBS_ON_MERGE_REQUESTS = 3


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
    index_directory_command = (
        "install -d -o 1000 -g 1000 -m 0750 /app/.tmp/public-search"
    )
    index_command = "python manage.py refresh_discovery_search --if-enabled --force"
    warm_command = "python manage.py warm_explorer_facets --refresh"

    assert index_directory_command in deploy
    assert index_command in deploy
    assert warm_command in deploy
    assert deploy.index(index_directory_command) < deploy.index(index_command)
    assert deploy.index(index_command) < deploy.index(warm_command)
    assert deploy.index(warm_command) > deploy.index("--wait-timeout 120")


def test_dev_web_and_worker_share_the_writable_public_index_path():
    compose = (REPO_ROOT / "docker-compose.dev.yml").read_text()
    index_path = "/app/.tmp/public-search/public-search-index.json"

    assert (
        compose.count(f'PUBLIC_SEARCH_INDEX_PATH: "{index_path}"')
        == DEV_PUBLIC_INDEX_CONSUMERS
    )


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


def test_deploy_restores_the_worker_when_interrupted_mid_sequence():
    """A deployment stops huey before recreating the web services and only
    restarts it once they are healthy. With `set -euo pipefail`, anything that
    aborts inside that window - a cancelled CI job, a health-check timeout -
    previously left the worker stopped with no automation to notice.
    """
    deploy = DEPLOY.read_text()

    # Bash runs an EXIT trap when the shell is terminated by HUP, INT or TERM,
    # so a cancelled job (dying ssh client -> HUP) already reaches cleanup.
    # Trapping those signals as well would run cleanup twice.
    assert "trap cleanup EXIT\n" in deploy
    assert "trap cleanup EXIT HUP" not in deploy

    # Restoration is best-effort so the trap can neither hang nor mask the
    # original exit status.
    assert "huey_stopped" in deploy
    restore_command = (
        'docker compose -f "${compose_file}" up -d --no-build --no-deps huey'
    )
    assert restore_command in deploy

    # The flag must be raised by every stop and cleared only after a
    # successful restart.
    assert deploy.count("huey_stopped=1") == deploy.count("stop -t 30 huey")
    assert deploy.count("huey_stopped=0") >= 1


def test_deploy_marks_the_worker_stopped_before_recreating_web_services():
    deploy = DEPLOY.read_text()

    first_flag = deploy.index("huey_stopped=1")
    first_web_recreate = deploy.index('for web_service in "${web_services[@]}"')

    assert first_flag < first_web_recreate


def test_validation_jobs_run_on_merge_requests():
    """Deploy jobs are the only automation on this repository, so an MR
    reaching dev is currently unchecked. Validation must run on merge requests.
    """
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    merge_request_rule = "- if: '$CI_PIPELINE_SOURCE == \"merge_request_event\"'"

    assert pipeline.count(merge_request_rule) >= VALIDATION_JOBS_ON_MERGE_REQUESTS


def test_deploy_jobs_never_run_on_merge_requests():
    """Deploy jobs key off $CI_COMMIT_BRANCH, which is unset in
    merge_request_event pipelines, so they cannot fire from an MR. Guard that
    invariant explicitly - a deploy triggered by an MR would be severe.
    """
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    deploy_jobs = (
        "deploy_dev_full",
        "deploy_dev_fast",
        "deploy_prod_full",
        "deploy_prod_fast",
    )
    for job in deploy_jobs:
        start = pipeline.index(f"{job}:")
        body = pipeline[start : pipeline.index("\n\n", start)]
        assert "merge_request_event" not in body, f"{job} must not run on an MR"
        assert "$CI_COMMIT_BRANCH ==" in body, f"{job} must stay branch-gated"


def test_javascript_tests_run_in_ci():
    """The jest suite covers the ELAN viewer and segment links; nothing ran it
    in CI before.
    """
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    assert "js_tests:" in pipeline
    assert "npx jest" in pipeline


def test_interrupted_deploy_actually_restarts_the_worker(tmp_path: Path):
    """Exercise the restoration path rather than asserting on source text.

    Reproduces the deploy script's stop-then-recreate window with a fake
    `docker` on PATH, kills the script mid-window the way a cancelled CI job
    does, and checks the worker was started again.
    """
    recorded = tmp_path / "docker-calls.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> {recorded}\n'
        # Block where the real script waits for web services to become healthy.
        'if [[ "$*" == *"--force-recreate"* ]]; then sleep 30; fi\n'
        "exit 0\n",
    )
    fake_docker.chmod(0o755)

    script = tmp_path / "window.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "compose_file=compose.yml\n"
        "log() { :; }\n"
        "huey_stopped=0\n"
        "cleanup() {\n"
        "  local status=$?\n"
        "  if (( huey_stopped )); then\n"
        '    docker compose -f "${compose_file}" up -d --no-build --no-deps huey'
        " </dev/null || true\n"
        "  fi\n"
        '  exit "${status}"\n'
        "}\n"
        "trap cleanup EXIT\n"
        'docker compose -f "${compose_file}" stop -t 30 huey\n'
        "huey_stopped=1\n"
        'docker compose -f "${compose_file}" up -d --force-recreate --wait django\n'
        "huey_stopped=0\n",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    process = subprocess.Popen(
        ["bash", str(script)],
        env=env,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Let it get past the stop and into the recreate wait, then cancel it.
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=2)
    process.terminate()
    process.wait(timeout=15)

    calls = recorded.read_text().splitlines()
    assert any("stop -t 30 huey" in call for call in calls), calls
    restarts = [c for c in calls if "up -d --no-build --no-deps huey" in c]
    assert len(restarts) == 1, f"worker not restored exactly once: {calls}"
