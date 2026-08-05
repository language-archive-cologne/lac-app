# ruff: noqa: INP001
"""Warm Explorer search pages through the running Gunicorn server."""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlsplit
from urllib.request import Request
from urllib.request import urlopen

SEARCH_PATHS = ("/search/", "/search/bundles/")
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_CONCURRENT_REQUESTS = 32
INVALID_BASE_URL_MESSAGE = "base_url must be an absolute HTTP(S) URL"
INVALID_REQUEST_COUNT_MESSAGE = "requests_per_page must be positive"
INVALID_TIMEOUT_MESSAGE = "timeout must be positive"


class PageWarmConfigurationError(ValueError):
    """The page warmer received an invalid configuration value."""


@dataclass(frozen=True)
class PageWarmResult:
    path: str
    status: int
    bytes_read: int
    duration_ms: float


def _validate_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PageWarmConfigurationError(INVALID_BASE_URL_MESSAGE)
    return normalized


def _warm_page(base_url: str, host: str, path: str, timeout: float) -> PageWarmResult:
    request = Request(  # noqa: S310 -- base URL is restricted to HTTP(S) above.
        f"{base_url}{path}",
        headers={
            "Host": host,
            "Connection": "close",
            "X-Forwarded-Proto": "https",
        },
    )
    started = perf_counter()
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read()
        status = response.status
    return PageWarmResult(
        path=path,
        status=status,
        bytes_read=len(body),
        duration_ms=(perf_counter() - started) * 1000,
    )


def warm_pages(
    *,
    base_url: str,
    host: str,
    requests_per_page: int,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[PageWarmResult]:
    """Request every search page repeatedly over separate concurrent connections."""
    if requests_per_page <= 0:
        raise PageWarmConfigurationError(INVALID_REQUEST_COUNT_MESSAGE)
    if timeout <= 0:
        raise PageWarmConfigurationError(INVALID_TIMEOUT_MESSAGE)
    normalized_base_url = _validate_base_url(base_url)
    tasks = [path for path in SEARCH_PATHS for _ in range(requests_per_page)]
    worker_count = min(len(tasks), MAX_CONCURRENT_REQUESTS)

    def execute(path: str) -> PageWarmResult:
        return _warm_page(normalized_base_url, host, path, timeout)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(execute, tasks))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        message = "must be positive"
        raise argparse.ArgumentTypeError(message)
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--host", default=os.environ.get("DJANGO_HEALTHCHECK_HOST"))
    parser.add_argument(
        "--requests-per-page",
        type=_positive_int,
        default=_positive_int(os.environ.get("GUNICORN_WORKERS", "4")),
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()
    if not args.host:
        parser.error("--host or DJANGO_HEALTHCHECK_HOST is required")

    results = warm_pages(
        base_url=args.base_url,
        host=args.host,
        requests_per_page=args.requests_per_page,
        timeout=args.timeout,
    )
    for result in results:
        sys.stdout.write(
            f"Warmed {result.path} ({result.status}, {result.bytes_read} bytes, "
            f"{result.duration_ms:.1f} ms)\n",
        )


if __name__ == "__main__":
    main()
