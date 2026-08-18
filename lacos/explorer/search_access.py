"""Short-lived, client-bound admission grants for expensive search requests."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.core.cache import cache

from lacos.common.request_utils import get_client_ip

SEARCH_ACCESS_COOKIE_NAME = "lacos_search_access"
SEARCH_ACCESS_SIGNING_SALT = "lacos.explorer.search-access.v1"
SEARCH_ACCESS_CACHE_PREFIX = "explorer:search-access"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchAccessGrant:
    """Signed cookie value and its browser lifetime."""

    value: str
    max_age: int


@dataclass(frozen=True)
class SearchAccessAuthorization:
    """Validated grant identifier that may be spent after capacity admission."""

    grant_id: str


class SearchAccessService:
    """Issue, validate, and spend finite grants after ALTCHA verification."""

    def issue(self, request) -> SearchAccessGrant:
        grant_id = secrets.token_urlsafe(24)
        max_age = self._max_age()
        cache.set(self._cache_key(grant_id), 0, timeout=max_age)
        value = signing.dumps(
            {"grant": grant_id, "fingerprint": self._fingerprint(request)},
            salt=SEARCH_ACCESS_SIGNING_SALT,
            compress=True,
        )
        return SearchAccessGrant(value=value, max_age=max_age)

    def validate(self, request) -> SearchAccessAuthorization | None:
        value = request.COOKIES.get(SEARCH_ACCESS_COOKIE_NAME)
        if not value:
            return None

        payload = self._load_payload(value)
        if payload is None:
            return None

        expected = self._fingerprint(request)
        supplied = str(payload.get("fingerprint", ""))
        grant_id = str(payload.get("grant", ""))
        if not grant_id or not hmac.compare_digest(supplied, expected):
            return None

        used = self._read_grant(grant_id)
        if not isinstance(used, int) or used < 0 or used >= self._request_budget():
            return None
        return SearchAccessAuthorization(grant_id=grant_id)

    def spend(self, authorization: SearchAccessAuthorization) -> bool:
        """Atomically spend a validated grant after search capacity is reserved."""
        used = self._increment_grant(authorization.grant_id)
        return isinstance(used, int) and used <= self._request_budget()

    def _load_payload(self, value: str) -> dict | None:
        try:
            payload = signing.loads(
                value,
                salt=SEARCH_ACCESS_SIGNING_SALT,
                max_age=self._max_age(),
            )
        except signing.BadSignature:
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    def _increment_grant(self, grant_id: str) -> int | None:
        try:
            return cache.incr(self._cache_key(grant_id))
        except (TypeError, ValueError):
            return None
        except Exception:
            logger.exception("Search grant cache unavailable")
            return None

    def _read_grant(self, grant_id: str) -> int | None:
        try:
            return cache.get(self._cache_key(grant_id))
        except Exception:
            logger.exception("Search grant cache unavailable")
            return None

    @staticmethod
    def _fingerprint(request) -> str:
        client_ip = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        return hashlib.sha256(f"{client_ip}\0{user_agent}".encode()).hexdigest()

    @staticmethod
    def _cache_key(grant_id: str) -> str:
        return f"{SEARCH_ACCESS_CACHE_PREFIX}:grant:{grant_id}"

    @staticmethod
    def _max_age() -> int:
        return settings.SEARCH_ALTCHA_ACCESS_TTL_SECONDS

    @staticmethod
    def _request_budget() -> int:
        return settings.SEARCH_ALTCHA_REQUEST_BUDGET


def get_search_access_service() -> SearchAccessService:
    return SearchAccessService()
