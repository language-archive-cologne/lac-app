"""Email-related settings helpers."""

from __future__ import annotations

from email.utils import getaddresses


def parse_admins(value: str) -> list[tuple[str, str]]:
    """Parse Django ADMINS from a comma-separated RFC 5322 address list."""
    return [
        (name or email, email)
        for name, email in getaddresses([value])
        if email
    ]
