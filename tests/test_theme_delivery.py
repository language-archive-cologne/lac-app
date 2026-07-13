from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
THEME_PACKAGE = REPO_ROOT / "theme" / "static_src" / "package.json"
THEME_LOCK = REPO_ROOT / "theme" / "static_src" / "package-lock.json"
PIPELINE = REPO_ROOT / ".gitlab-ci.yml"


def test_theme_uses_the_locked_local_tailwind_binary():
    package = json.loads(THEME_PACKAGE.read_text())

    assert package["scripts"]["build"].startswith("tailwindcss ")
    assert package["scripts"]["dev"].startswith("tailwindcss ")
    assert "npx" not in package["scripts"]["build"]


def test_theme_lockfile_contains_the_patched_picomatch_release():
    lockfile = json.loads(THEME_LOCK.read_text())

    assert lockfile["packages"]["node_modules/picomatch"]["version"] == "2.3.2"


def test_pipeline_audits_builds_and_exports_the_theme_artifact():
    pipeline = PIPELINE.read_text()

    assert "theme_build:" in pipeline
    assert "npm ci --no-audit --no-fund" in pipeline
    assert "npm audit --audit-level=high" in pipeline
    assert "npm run build" in pipeline
    assert "theme/static/css/output.css" in pipeline
    assert '$CI_PIPELINE_SOURCE != "schedule"' in pipeline
