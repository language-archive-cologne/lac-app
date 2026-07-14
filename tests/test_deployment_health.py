from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = ("docker-compose.dev.yml", "docker-compose.production.yml")


def _django_service_block(compose_file: Path) -> str:
    content = compose_file.read_text()
    start = content.index("  django:\n")
    end = content.index("\n  pgbouncer:\n", start)
    return content[start:end]


def test_deployed_django_services_have_a_startup_aware_healthcheck():
    for filename in COMPOSE_FILES:
        django = _django_service_block(REPO_ROOT / filename)

        assert "healthcheck:" in django
        assert "socket.create_connection" in django
        assert "127.0.0.1" in django
        assert "8000" in django
        assert "start_period: 60s" in django
        assert "retries: 12" in django
