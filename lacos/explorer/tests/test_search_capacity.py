"""Tests for verified-search aggregate capacity."""

from unittest.mock import patch

from django.test import override_settings

from lacos.explorer.search_capacity import SearchCapacityService


@override_settings(SEARCH_MAX_CONCURRENT_REQUESTS=2)
def test_capacity_fails_closed_when_cache_is_unavailable():
    service = SearchCapacityService()

    with patch(
        "lacos.explorer.search_capacity.cache.incr",
        side_effect=RuntimeError("cache unavailable"),
    ):
        assert service.acquire() is False
