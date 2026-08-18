"""Production search safeguards must be configured outside version control."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_SETTINGS = REPO_ROOT / "config" / "settings" / "base.py"
PRODUCTION_SETTINGS = REPO_ROOT / "config" / "settings" / "production.py"

PRIVATE_SEARCH_SETTINGS = (
    "SEARCH_ALTCHA_ACCESS_TTL_SECONDS",
    "SEARCH_ALTCHA_VERIFY_RATE_LIMIT",
    "SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS",
    "SEARCH_GRANT_RATE_LIMIT",
    "SEARCH_GRANT_RATE_WINDOW_SECONDS",
    "SEARCH_MAX_CONCURRENT_REQUESTS",
    "SEARCH_CAPACITY_SLOT_TIMEOUT_SECONDS",
    "SEARCH_CAPACITY_RETRY_SECONDS",
)


def test_base_settings_contain_no_operational_search_limits():
    source = BASE_SETTINGS.read_text()

    for name in PRIVATE_SEARCH_SETTINGS:
        assert f'{name} = env.int("{name}", default=0)' in source


def test_production_requires_private_search_limits_from_the_environment():
    source = PRODUCTION_SETTINGS.read_text()

    assert 'SEARCH_ALTCHA_ENABLED = env.bool("SEARCH_ALTCHA_ENABLED")' in source
    for name in PRIVATE_SEARCH_SETTINGS:
        assert f'{name} = env.int("{name}")' in source
    assert "if _setting_value < 1:" in source
    assert "raise ImproperlyConfigured(message)" in source
