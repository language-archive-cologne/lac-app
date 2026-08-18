"""Small fixed-window rate limits backed by Django's shared cache."""

from __future__ import annotations

import logging

from django.core.cache import cache

from lacos.common.request_utils import get_client_ip

logger = logging.getLogger(__name__)


def check_rate_limit(request, key_prefix: str, limit: int, window_seconds: int) -> bool:
    """Atomically admit at most ``limit`` requests per client and window."""
    cache_key = f"ratelimit:{key_prefix}:{get_client_ip(request)}"
    try:
        count = _increment_counter(cache_key, window_seconds)
    except Exception:
        logger.exception("Rate limit cache unavailable", extra={"cache_key": cache_key})
        return False
    return isinstance(count, int) and count <= limit


def _increment_counter(cache_key: str, window_seconds: int) -> int:
    try:
        return cache.incr(cache_key)
    except ValueError:
        if cache.add(cache_key, 1, timeout=window_seconds):
            return 1
        return cache.incr(cache_key)
