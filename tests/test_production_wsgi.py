from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
START_PRODUCTION = REPO_ROOT / "compose" / "production" / "django" / "start"
START_LOCAL = REPO_ROOT / "compose" / "local" / "django" / "start"


def _gunicorn_line() -> str:
    script = START_PRODUCTION.read_text().replace("\\\n", " ")
    for line in script.splitlines():
        if "gunicorn" in line and not line.lstrip().startswith("#"):
            return line
    msg = "no gunicorn invocation found in production start script"
    raise AssertionError(msg)


def test_production_serves_wsgi_not_asgi():
    """ASGI cancels request handling when clients disconnect, leaking the
    request's database connection until garbage collection. Scraper bursts
    of aborted requests exhausted PgBouncer's max_client_conn this way.
    The app has no async views, so production must run the WSGI application.
    """
    line = _gunicorn_line()

    assert "config.wsgi" in line
    assert "asgi" not in line
    assert "Uvicorn" not in line and "uvicorn" not in line


def test_production_gunicorn_bounds_concurrency():
    """Worker and thread counts cap concurrent requests, which caps client
    connections held against PgBouncer (must stay well below max_client_conn
    and aligned with the server pool size)."""
    line = _gunicorn_line()

    workers = re.search(r"--workers \"?\$\{GUNICORN_WORKERS:-(\d+)\}", line)
    threads = re.search(r"--threads \"?\$\{GUNICORN_THREADS:-(\d+)\}", line)
    assert workers, "gunicorn must set an explicit --workers count"
    assert threads, "gunicorn must set an explicit --threads count"
    concurrency = int(workers.group(1)) * int(threads.group(1))
    assert concurrency <= 40, "concurrency must not exceed PgBouncer server pool"


def test_dev_stack_uses_the_production_start_script():
    """The deployed dev stack must not run the reload dev server; it serves
    the same WSGI configuration as production."""
    compose = (REPO_ROOT / "docker-compose.dev.yml").read_text()
    django_block = compose[compose.index("  django:\n") : compose.index("\n  pgbouncer:\n")]

    assert "command: /start-production" in django_block


def test_local_dev_server_serves_wsgi():
    """Local development keeps autoreload but must exercise the same WSGI
    application as production (ASGI leaked DB connections on client aborts)."""
    script = START_LOCAL.read_text()

    assert "config.wsgi" in script
    assert "config.asgi" not in script
    assert "--reload" in script


def test_local_compose_runs_the_start_script():
    """The local compose file must not inline its own server command,
    which would silently bypass the start script's WSGI configuration."""
    compose = (REPO_ROOT / "docker-compose.local.yml").read_text()
    django_block = compose[compose.index("  django:\n") : compose.index("\n  pgbouncer:\n")]

    assert "command: /start\n" in django_block
    assert "uvicorn" not in django_block
