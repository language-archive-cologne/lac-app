from __future__ import annotations

from django.conf import settings


def get_client_ip(request) -> str:
    """Return the client IP, trusting forwarded headers only from known proxies."""
    if request is None:
        return "unknown"

    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    trusted_proxies = set(getattr(settings, "TRUSTED_PROXY_IPS", []) or [])

    if remote_addr in trusted_proxies:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

    return remote_addr
