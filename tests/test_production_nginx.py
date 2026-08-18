"""Regression coverage for the production search traffic boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NGINX_CONFIG = REPO_ROOT / "config" / "nginx" / "lacos.uni-koeln.de"
PRIVATE_TEMPLATES = REPO_ROOT / "config" / "nginx" / "private-templates"
PRODUCTION_COMPOSE = REPO_ROOT / "docker-compose.production.yml"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "verify-nginx-config.sh"
EXPECTED_PROXY_HEADER_COUNT = 2


def _config() -> str:
    return NGINX_CONFIG.read_text()


def test_search_location_covers_collection_and_bundle_routes():
    config = _config()

    assert "location ^~ /search/" in config
    assert "location /search/bundles/" not in config


def test_search_location_enforces_layered_request_limits():
    config = _config()

    assert "include /etc/nginx/lacos-private/search-zones.conf;" in config
    assert "include /etc/nginx/lacos-private/search-location-limits.conf;" in config


def test_application_routes_use_the_private_emergency_capacity_boundary():
    config = _config()
    application_location = config.split("location / {", 1)[1].split(
        "\n    }",
        1,
    )[0]

    assert (
        "include /etc/nginx/lacos-private/application-location-limits.conf;"
        in application_location
    )

    private_limits = (
        PRIVATE_TEMPLATES / "application-location-limits.conf.template"
    ).read_text()
    assert "limit_req zone=lacos_emergency_requests" in private_limits
    assert "limit_conn lacos_emergency_connections" in private_limits
    assert "error_page 503 @application_capacity_limited" in private_limits


def test_private_search_template_layers_client_and_emergency_boundaries():
    zones = (PRIVATE_TEMPLATES / "search-zones.conf.template").read_text()
    search_limits = (
        PRIVATE_TEMPLATES / "search-location-limits.conf.template"
    ).read_text()

    assert "zone=lacos_search_per_ip:${LACOS_SEARCH_ZONE_SIZE}" in zones
    assert "zone=lacos_emergency_requests:${LACOS_EMERGENCY_REQUEST_ZONE_SIZE}" in zones
    assert (
        "zone=lacos_emergency_connections:${LACOS_EMERGENCY_CONNECTION_ZONE_SIZE}"
        in zones
    )
    assert "limit_req zone=lacos_search_per_ip" in search_limits
    assert "limit_req zone=lacos_emergency_requests" in search_limits
    assert "limit_conn lacos_emergency_connections" in search_limits


def test_search_limits_do_not_trust_client_supplied_cookie_values():
    config = _config()

    assert "$cookie_lacos_search_access" not in config
    assert "lacos_search_grant" not in config
    assert "lacos_search_unverified" not in config


def test_operational_limit_values_are_not_committed():
    config = _config()

    assert "limit_req_zone" not in config
    assert "limit_conn_zone" not in config
    assert " burst=" not in config
    assert "rate=" not in config


def test_search_rejects_keyword_selections_over_the_application_budget():
    config = _config()

    assert "if ($lacos_search_too_many_keywords)" in config
    assert "keyword=.*keyword=" not in config


def test_search_limits_return_retryable_429_responses():
    config = _config()

    assert "error_page 429 @search_rate_limited" in config
    assert "add_header Retry-After $lacos_search_retry_after always" in config


def test_search_proxy_has_a_bounded_request_window():
    config = _config()
    search_location = config.split("location ^~ /search/ {", 1)[1].split(
        "\n    }",
        1,
    )[0]

    assert "proxy_read_timeout 35s" in search_location
    assert "proxy_send_timeout 35s" in search_location


def test_search_limits_use_the_restored_real_client_address():
    config = _config()

    assert "set_real_ip_from 134.95.126.48/29" in config
    assert "real_ip_header   X-Forwarded-For" in config
    assert (
        config.count("proxy_set_header X-Forwarded-For   $remote_addr;")
        == EXPECTED_PROXY_HEADER_COUNT
    )


def test_django_trusts_only_the_internal_docker_proxy_network():
    compose = PRODUCTION_COMPOSE.read_text()

    assert 'TRUSTED_PROXY_CIDRS: "172.16.0.0/12"' in compose
    assert "127.0.0.1:8103:8000" in compose


def test_pipeline_validates_the_nginx_configuration():
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    assert "production_nginx_config:" in pipeline
    assert "config/nginx/lacos.uni-koeln.de" in pipeline
    assert "nginx -t" in pipeline


def test_production_deploy_verifies_live_nginx_configuration():
    deploy = (REPO_ROOT / "scripts" / "deploy" / "deploy.sh").read_text()

    assert "verify-nginx-config.sh" in deploy
    assert "/etc/nginx/sites-enabled/lacos.uni-koeln.de" in deploy


def test_production_deploy_does_not_warm_search_without_a_grant():
    deploy = (REPO_ROOT / "scripts" / "deploy" / "deploy.sh").read_text()

    assert "warm_explorer_facets --refresh" in deploy
    assert "warm_pages.py" not in deploy


def _verify(
    expected: Path,
    installed: Path,
    private_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["bash", str(VERIFY_SCRIPT), str(expected), str(installed)]
    if private_root is not None:
        command.append(str(private_root))
    return subprocess.run(  # noqa: S603 -- arguments are local test paths.
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def test_nginx_verifier_accepts_an_exact_match(tmp_path: Path):
    expected = tmp_path / "expected"
    installed = tmp_path / "installed"
    expected.write_text("server {}\n")
    installed.write_text("server {}\n")

    result = _verify(expected, installed)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["expected", "installed"])
def test_nginx_verifier_rejects_missing_files(tmp_path: Path, missing: str):
    expected = tmp_path / "expected"
    installed = tmp_path / "installed"
    if missing != "expected":
        expected.write_text("server {}\n")
    if missing != "installed":
        installed.write_text("server {}\n")

    result = _verify(expected, installed)

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_nginx_verifier_rejects_configuration_drift(tmp_path: Path):
    expected = tmp_path / "expected"
    installed = tmp_path / "installed"
    expected.write_text("server { listen 80; }\n")
    installed.write_text("server { listen 8080; }\n")

    result = _verify(expected, installed)

    assert result.returncode != 0
    assert "differs from reviewed config" in result.stderr


def test_nginx_verifier_requires_nonempty_private_limit_files(tmp_path: Path):
    expected = tmp_path / "expected"
    installed = tmp_path / "installed"
    private_root = tmp_path / "private"
    private_root.mkdir()
    config = "include /etc/nginx/lacos-private/search-zones.conf;\n"
    expected.write_text(config)
    installed.write_text(config)

    missing = _verify(expected, installed, private_root)
    (private_root / "search-zones.conf").touch()
    empty = _verify(expected, installed, private_root)

    assert missing.returncode != 0
    assert "does not exist" in missing.stderr
    assert empty.returncode != 0
    assert "is empty" in empty.stderr


def test_nginx_verifier_accepts_private_limit_files(tmp_path: Path):
    expected = tmp_path / "expected"
    installed = tmp_path / "installed"
    private_root = tmp_path / "private"
    private_root.mkdir()
    config = "include /etc/nginx/lacos-private/search-zones.conf;\n"
    expected.write_text(config)
    installed.write_text(config)
    (private_root / "search-zones.conf").write_text(
        "limit_req_zone $binary_remote_addr zone=lacos_search_per_ip:VALUE "
        "rate=VALUE;\n"
        "limit_req_zone $server_name zone=lacos_emergency_requests:VALUE "
        "rate=VALUE;\n"
        "limit_conn_zone $server_name zone=lacos_emergency_connections:VALUE;\n"
        "map $args $lacos_search_too_many_keywords { default 0; }\n"
        'map "" $lacos_search_retry_after { default VALUE; }\n'
        'map "" $lacos_capacity_retry_after { default VALUE; }\n',
    )

    result = _verify(expected, installed, private_root)

    assert result.returncode == 0, result.stderr
