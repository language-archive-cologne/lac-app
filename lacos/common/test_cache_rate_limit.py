"""Tests for shared-cache request limiting."""

from unittest.mock import patch

from django.test import RequestFactory

from lacos.common.cache_rate_limit import check_rate_limit


def test_rate_limit_fails_closed_when_cache_is_unavailable():
    request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.10")

    with patch(
        "lacos.common.cache_rate_limit.cache.incr",
        side_effect=RuntimeError("cache unavailable"),
    ):
        admitted = check_rate_limit(request, "test", limit=10, window_seconds=60)

    assert admitted is False
