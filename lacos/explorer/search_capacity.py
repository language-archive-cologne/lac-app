"""Aggregate capacity reserved only for verified search requests."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

SEARCH_CAPACITY_CACHE_KEY = "explorer:search-capacity:active"


class SearchCapacityService:
    """Bound concurrent database search work with an expiring cache counter."""

    def acquire(self) -> bool:
        try:
            active = cache.incr(SEARCH_CAPACITY_CACHE_KEY)
        except ValueError:
            active = self._create_counter()
        except Exception:
            logger.exception("Search capacity cache increment failed")
            return False

        if not isinstance(active, int):
            return False
        if active <= settings.SEARCH_MAX_CONCURRENT_REQUESTS:
            return True

        self.release()
        return False

    def _create_counter(self) -> int | None:
        try:
            if cache.add(
                SEARCH_CAPACITY_CACHE_KEY,
                1,
                timeout=settings.SEARCH_CAPACITY_SLOT_TIMEOUT_SECONDS,
            ):
                return 1
            return cache.incr(SEARCH_CAPACITY_CACHE_KEY)
        except Exception:
            logger.exception("Search capacity cache initialization failed")
            return None

    def release(self) -> None:
        try:
            cache.decr(SEARCH_CAPACITY_CACHE_KEY)
        except ValueError:
            return
        except Exception:
            logger.exception("Search capacity cache release failed")

    @contextmanager
    def reserve(self):
        acquired = self.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


def get_search_capacity_service() -> SearchCapacityService:
    return SearchCapacityService()
