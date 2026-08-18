from __future__ import annotations

from ipaddress import ip_address
from ipaddress import ip_network

from django.conf import settings


def _is_trusted_proxy(remote_addr: str) -> bool:
    if remote_addr in set(getattr(settings, "TRUSTED_PROXY_IPS", []) or []):
        return True

    try:
        address = ip_address(remote_addr)
    except ValueError:
        return False

    for cidr in getattr(settings, "TRUSTED_PROXY_CIDRS", []) or []:
        try:
            if address in ip_network(cidr):
                return True
        except ValueError:
            continue
    return False


def get_client_ip(request) -> str:
    """Return the client IP, trusting forwarded headers only from known proxies."""
    if request is None:
        return "unknown"

    remote_addr = request.META.get("REMOTE_ADDR", "unknown")

    if _is_trusted_proxy(remote_addr):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()

    return remote_addr
