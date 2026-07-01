"""Rate limiting for Django admin error emails."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import caches

DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_IDENTICAL_LIMIT = 3
DEFAULT_TOTAL_LIMIT = 20
DEFAULT_DISALLOWED_HOST_LIMIT = 1


@dataclass(frozen=True)
class AdminEmailRateLimitConfig:
    enabled: bool
    window_seconds: int
    identical_limit: int
    total_limit: int
    disallowed_host_limit: int
    key_prefix: str


def get_admin_email_rate_limit_config() -> AdminEmailRateLimitConfig:
    """Read rate limit settings at filter time so tests and overrides work."""
    return AdminEmailRateLimitConfig(
        enabled=getattr(settings, "ADMIN_EMAIL_RATE_LIMIT_ENABLED", True),
        window_seconds=getattr(
            settings,
            "ADMIN_EMAIL_RATE_LIMIT_WINDOW_SECONDS",
            DEFAULT_WINDOW_SECONDS,
        ),
        identical_limit=getattr(
            settings,
            "ADMIN_EMAIL_RATE_LIMIT_IDENTICAL_LIMIT",
            DEFAULT_IDENTICAL_LIMIT,
        ),
        total_limit=getattr(
            settings,
            "ADMIN_EMAIL_RATE_LIMIT_TOTAL_LIMIT",
            DEFAULT_TOTAL_LIMIT,
        ),
        disallowed_host_limit=getattr(
            settings,
            "ADMIN_EMAIL_RATE_LIMIT_DISALLOWED_HOST_LIMIT",
            DEFAULT_DISALLOWED_HOST_LIMIT,
        ),
        key_prefix=getattr(
            settings,
            "ADMIN_EMAIL_RATE_LIMIT_KEY_PREFIX",
            "admin-email-rate-limit",
        ),
    )


def build_admin_email_fingerprint(record: logging.LogRecord) -> str:
    """Build a stable fingerprint without request supplied secrets or query data."""
    request = getattr(record, "request", None)
    path_pattern = _request_path_pattern(request)
    exception_class = _exception_class(record)
    frame = _top_application_frame(record)
    raw = "|".join(
        (
            record.name,
            str(record.levelno),
            str(getattr(record, "status_code", "")),
            path_pattern,
            exception_class,
            frame,
        ),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AdminEmailRateLimitFilter(logging.Filter):
    """Suppress duplicate and high volume Django admin error emails."""

    def __init__(self, name: str = "", cache_alias: str = "default") -> None:
        super().__init__(name)
        self.cache_alias = cache_alias

    def filter(self, record: logging.LogRecord) -> bool:
        config = get_admin_email_rate_limit_config()
        if not config.enabled:
            return True

        fingerprint_limit = self._fingerprint_limit(record, config)
        fingerprint = build_admin_email_fingerprint(record)

        fingerprint_count = self._increment_counter(
            f"{config.key_prefix}:fingerprint:{fingerprint}",
            config.window_seconds,
        )
        if fingerprint_count is None or fingerprint_count > fingerprint_limit:
            return False

        total_count = self._increment_counter(
            f"{config.key_prefix}:total",
            config.window_seconds,
        )
        return total_count is not None and total_count <= config.total_limit

    def _fingerprint_limit(
        self,
        record: logging.LogRecord,
        config: AdminEmailRateLimitConfig,
    ) -> int:
        if record.name == "django.security.DisallowedHost":
            return config.disallowed_host_limit
        return config.identical_limit

    def _increment_counter(self, key: str, timeout: int) -> int | None:
        cache = caches[self.cache_alias]
        try:
            cache.add(key, 0, timeout=timeout)
            return cache.incr(key)
        except Exception:  # noqa: BLE001
            return None


def _request_path_pattern(request: object | None) -> str:
    if request is None:
        return ""
    resolver_match = getattr(request, "resolver_match", None)
    route = getattr(resolver_match, "route", None)
    if route:
        return str(route)
    path_info = getattr(request, "path_info", None)
    if path_info:
        return str(path_info)
    return ""


def _exception_class(record: logging.LogRecord) -> str:
    if record.exc_info and record.exc_info[0]:
        return record.exc_info[0].__name__
    exc = getattr(record, "exc", None)
    if exc:
        return exc.__class__.__name__
    return ""


def _top_application_frame(record: logging.LogRecord) -> str:
    if not record.exc_info or not record.exc_info[2]:
        return f"{record.pathname}:{record.funcName}:{record.lineno}"

    traceback = record.exc_info[2]
    selected = traceback
    while traceback:
        filename = traceback.tb_frame.f_code.co_filename
        if "/lacos/" in filename or "/config/" in filename:
            selected = traceback
        traceback = traceback.tb_next

    code = selected.tb_frame.f_code
    return f"{code.co_filename}:{code.co_name}:{selected.tb_lineno}"
