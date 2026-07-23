from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
START_PRODUCTION = REPO_ROOT / "compose" / "production" / "django" / "start"


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
