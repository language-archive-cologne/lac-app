"""Regression coverage for the production search traffic boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NGINX_CONFIG = REPO_ROOT / "config" / "nginx" / "lacos.uni-koeln.de"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "verify-nginx-config.sh"


def _config() -> str:
    return NGINX_CONFIG.read_text()


def test_search_location_covers_collection_and_bundle_routes():
    config = _config()

    assert "location ^~ /search/" in config
    assert "location /search/bundles/" not in config


def test_search_location_enforces_layered_request_limits():
    config = _config()

    assert "$binary_remote_addr zone=lacos_search_per_ip:10m rate=60r/m" in config
    assert "$server_name zone=lacos_search_global:1m rate=600r/m" in config
    assert "$server_name zone=lacos_search_concurrency" in config
    assert "limit_req zone=lacos_search_per_ip burst=20 nodelay" in config
    assert "limit_req zone=lacos_search_global burst=100 nodelay" in config
    assert "limit_conn lacos_search_concurrency" in config


def test_search_rejects_keyword_selections_over_the_application_budget():
    config = _config()

    assert "map $args $lacos_search_too_many_keywords" in config
    assert "keyword=.*keyword=.*keyword=.*keyword=.*keyword=" in config
    assert "if ($lacos_search_too_many_keywords)" in config
    assert 'return 422 "Select no more than four values per search facet.\\n"' in config


def test_search_limits_return_retryable_429_responses():
    config = _config()

    assert "limit_req_status 429" in config
    assert "limit_conn_status 429" in config
    assert "error_page 429 @search_rate_limited" in config
    assert "add_header Retry-After 10 always" in config


def test_search_proxy_has_a_bounded_request_window():
    config = _config()
    search_location = config.split("location ^~ /search/ {", 1)[1].split("\n    }", 1)[0]

    assert "proxy_read_timeout 35s" in search_location
    assert "proxy_send_timeout 35s" in search_location


def test_search_limits_use_the_restored_real_client_address():
    config = _config()

    assert "set_real_ip_from 134.95.126.48/29" in config
    assert "real_ip_header   X-Forwarded-For" in config


def test_pipeline_validates_the_nginx_configuration():
    pipeline = (REPO_ROOT / ".gitlab-ci.yml").read_text()

    assert "production_nginx_config:" in pipeline
    assert "config/nginx/lacos.uni-koeln.de" in pipeline
    assert "nginx -t" in pipeline


def test_production_deploy_verifies_live_nginx_configuration():
    deploy = (REPO_ROOT / "scripts" / "deploy" / "deploy.sh").read_text()

    assert "verify-nginx-config.sh" in deploy
    assert "/etc/nginx/sites-enabled/lacos.uni-koeln.de" in deploy


def _verify(expected: Path, installed: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(VERIFY_SCRIPT), str(expected), str(installed)],
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
