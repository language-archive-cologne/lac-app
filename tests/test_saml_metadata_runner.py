# These tests execute only repository scripts with controlled local tools.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_METADATA = REPO_ROOT / "scripts" / "validate_saml_metadata.sh"


def _run_generate_only(
    tmp_path: Path,
    *,
    root_generator: str | None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" > "$DOCKER_LOG"\n'
        'mkdir -p "$SAML_PREFLIGHT_WORK_DIR"\n'
        "printf '<EntityDescriptor />\\n' > "
        '"$SAML_PREFLIGHT_WORK_DIR/metadata.xml"\n',
    )
    fake_docker.chmod(0o755)
    key_file = tmp_path / "sp-key.pem"
    cert_file = tmp_path / "sp-cert.pem"
    key_file.write_text("key\n")
    cert_file.write_text("certificate\n")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "DOCKER_LOG": str(docker_log),
            "SAML_PREFLIGHT_WORK_DIR": str(tmp_path / "work"),
            "SAML_PREFLIGHT_SP_KEY_FILE": str(key_file),
            "SAML_PREFLIGHT_SP_CERT_FILE": str(cert_file),
        },
    )
    if root_generator is not None:
        env["SAML_PREFLIGHT_ROOT_GENERATOR"] = root_generator

    result = subprocess.run(
        ["bash", str(VALIDATE_METADATA), "--generate-only"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, docker_log


@pytest.mark.parametrize(
    ("root_generator", "expected_security_arguments"),
    [
        (
            "1",
            "--user 0:0 --cap-drop ALL --cap-add DAC_OVERRIDE --entrypoint python",
        ),
        (None, None),
    ],
)
def test_saml_metadata_generator_configures_the_requested_security_boundary(
    tmp_path: Path,
    root_generator: str | None,
    expected_security_arguments: str | None,
):
    result, docker_log = _run_generate_only(
        tmp_path,
        root_generator=root_generator,
    )

    assert result.returncode == 0, result.stderr
    invocation = docker_log.read_text()
    assert "--interactive=false --no-TTY" in invocation
    if expected_security_arguments is None:
        assert "--user" not in invocation
    else:
        assert expected_security_arguments in invocation
        assert "--privileged" not in invocation


def test_saml_metadata_generator_rejects_an_unsafe_root_mode(tmp_path: Path):
    result, docker_log = _run_generate_only(
        tmp_path,
        root_generator="1 --privileged",
    )

    assert result.returncode != 0
    assert "must be 0 or 1" in result.stderr
    assert not docker_log.exists()
