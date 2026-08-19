"""Production search safeguards must be configured outside version control."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_SETTINGS = REPO_ROOT / "config" / "settings" / "base.py"
PRODUCTION_SETTINGS = REPO_ROOT / "config" / "settings" / "production.py"
PRODUCTION_COMPOSE = REPO_ROOT / "docker-compose.production.yml"
PUBLIC_INDEX_SERVICES = ("django", "search", "huey")
PUBLIC_INDEX_PATH = "/app/.tmp/public-search/public-search-index.json"

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


def test_production_search_services_share_synchronized_public_index():
    services = yaml.safe_load(PRODUCTION_COMPOSE.read_text())["services"]

    for service_name in PUBLIC_INDEX_SERVICES:
        environment = services[service_name]["environment"]
        assert environment["PUBLIC_SEARCH_INDEX_ENABLED"] == "true"
        assert environment["PUBLIC_SEARCH_INDEX_PATH"] == PUBLIC_INDEX_PATH
        assert environment["DISCOVERY_REFRESH_ENABLED"] == "true"
        assert environment["DISCOVERY_REFRESH_DEBOUNCE_SECONDS"] == "30"
