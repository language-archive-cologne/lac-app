from __future__ import annotations

import sys
from collections import Counter
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError

import pytest

from scripts.deploy.warm_pages import SEARCH_PATHS
from scripts.deploy.warm_pages import main
from scripts.deploy.warm_pages import warm_pages

HTTP_OK = 200
HTTP_UNAVAILABLE = 503


class _RecordingHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, str]] = []
    failing_path: str | None = None

    def do_GET(self) -> None:
        type(self).requests.append(
            (
                self.path,
                self.headers["Host"],
                self.headers["X-Forwarded-Proto"],
            ),
        )
        status = HTTP_UNAVAILABLE if self.path == type(self).failing_path else HTTP_OK
        body = f"response for {self.path}".encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args: object) -> None:
        pass


@pytest.fixture
def page_server():
    _RecordingHandler.requests = []
    _RecordingHandler.failing_path = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_warm_pages_requests_each_search_page_concurrently(page_server):
    results = warm_pages(
        base_url=page_server,
        host="lacos.example.test",
        requests_per_page=4,
        timeout=2,
    )

    assert Counter(result.path for result in results) == dict.fromkeys(SEARCH_PATHS, 4)
    assert all(result.status == HTTP_OK for result in results)
    assert all(result.bytes_read > 0 for result in results)
    assert Counter(_RecordingHandler.requests) == {
        (path, "lacos.example.test", "https"): 4 for path in SEARCH_PATHS
    }


def test_warm_pages_cli_uses_container_environment(
    page_server,
    monkeypatch,
    capsys,
):
    monkeypatch.setenv("DJANGO_HEALTHCHECK_HOST", "lacos.example.test")
    monkeypatch.setenv("GUNICORN_WORKERS", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        ["warm_pages.py", "--base-url", page_server],
    )

    main()

    assert capsys.readouterr().out.count("Warmed /search") == len(SEARCH_PATHS)
    assert len(_RecordingHandler.requests) == len(SEARCH_PATHS)


def test_warm_pages_rejects_non_positive_request_count(page_server):
    with pytest.raises(ValueError, match="requests_per_page must be positive"):
        warm_pages(
            base_url=page_server,
            host="lacos.example.test",
            requests_per_page=0,
        )


def test_warm_pages_fails_when_a_search_page_is_unavailable(page_server):
    _RecordingHandler.failing_path = "/search/bundles/"

    with pytest.raises(HTTPError) as error:
        warm_pages(
            base_url=page_server,
            host="lacos.example.test",
            requests_per_page=1,
            timeout=2,
        )

    assert error.value.code == HTTP_UNAVAILABLE
