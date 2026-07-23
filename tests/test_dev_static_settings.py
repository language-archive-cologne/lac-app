from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_SETTINGS = REPO_ROOT / "config" / "settings" / "dev.py"


def test_dev_local_static_disables_collectfasta():
    """dev.py inherits collectfasta (boto3 strategy) from production but can
    override STORAGES to local StaticFilesStorage; collectstatic then crashes
    with "'StaticFilesStorage' object has no attribute 'entries'" unless
    collectfasta is disabled alongside the storage override."""
    source = DEV_SETTINGS.read_text()

    local_static_override = source.index("django.contrib.staticfiles.storage.StaticFilesStorage")
    assert "COLLECTFASTA_ENABLED = False" in source[local_static_override:]
