# These tests execute only repository scripts with controlled local tools.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_HELPER = (
    REPO_ROOT / "compose" / "production" / "django" / "ensure-staticfiles-ownership"
)
ENTRYPOINT = REPO_ROOT / "compose" / "production" / "django" / "entrypoint"
DOCKERFILE = REPO_ROOT / "compose" / "local" / "django" / "Dockerfile"


def test_staticfiles_helper_repairs_only_mismatched_paths(tmp_path: Path):
    static_root = tmp_path / "staticfiles"
    static_root.mkdir()
    static_file = static_root / "app.css"
    static_file.write_text("body {}\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    chown_log = tmp_path / "chown.log"
    fake_chown = fake_bin / "chown"
    fake_chown.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$CHOWN_LOG"\n')
    fake_chown.chmod(0o755)
    target_uid = os.getuid() + 1
    target_gid = os.getgid()
    env = os.environ.copy()
    env.update(
        {
            "CHOWN_LOG": str(chown_log),
            "PATH": f"{fake_bin}:{env['PATH']}",
        },
    )

    result = subprocess.run(
        [
            "bash",
            str(OWNERSHIP_HELPER),
            str(static_root),
            str(target_uid),
            str(target_gid),
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    log = chown_log.read_text()
    assert f"--no-dereference {target_uid}:{target_gid} {static_root}" in log
    assert f"--no-dereference {target_uid}:{target_gid} {static_file}" in log


def test_staticfiles_helper_rejects_a_symlinked_root(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    static_root = tmp_path / "staticfiles"
    static_root.symlink_to(target, target_is_directory=True)

    result = subprocess.run(
        [
            "bash",
            str(OWNERSHIP_HELPER),
            str(static_root),
            str(os.getuid()),
            str(os.getgid()),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "must not be a symlink" in result.stderr.lower()


def test_image_repairs_staticfiles_before_dropping_privileges():
    dockerfile = DOCKERFILE.read_text()
    entrypoint = ENTRYPOINT.read_text()

    assert "ensure-staticfiles-ownership /ensure-staticfiles-ownership" in dockerfile
    repair = entrypoint.index("/ensure-staticfiles-ownership")
    privilege_drop = entrypoint.index('exec gosu dev-user "$@"')
    assert repair < privilege_drop
