"""Application readiness checks for container orchestration."""

from __future__ import annotations

import logging
from uuid import uuid4

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


class ReadinessCheckError(RuntimeError):
    """A dependency returned an invalid readiness result."""


def check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        if cursor.fetchone() != (1,):
            raise ReadinessCheckError


def check_cache() -> None:
    key = f"health:readiness:{uuid4().hex}"
    value = uuid4().hex
    try:
        cache.set(key, value, timeout=5)
        if cache.get(key) != value:
            raise ReadinessCheckError
    finally:
        cache.delete(key)


@require_GET
def readiness_view(request):
    checks = {}
    for name, checker in (("database", check_database), ("cache", check_cache)):
        try:
            checker()
        except Exception:  # noqa: BLE001 -- readiness must contain dependency errors.
            logger.warning("Readiness check failed: %s", name, exc_info=True)
            checks[name] = "failed"
        else:
            checks[name] = "ok"

    ready = all(status == "ok" for status in checks.values())
    return JsonResponse(
        {"status": "ready" if ready else "unavailable", "checks": checks},
        status=200 if ready else 503,
    )
