"""
Signal handlers and utilities for SAML / Shibboleth integration.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.dispatch import receiver

from .adapters import TRUSTED_SAML_SESSION_KEY
from .models import User

try:
    from djangosaml2.signals import post_authenticated, pre_user_save
except ImportError:  # pragma: no cover - optional dependency guard
    post_authenticated = None  # type: ignore[assignment]
    pre_user_save = None  # type: ignore[assignment]

USERNAME_ATTR_KEYS: tuple[str, ...] = (
    "eduPersonPrincipalName",
    "urn:oid:1.3.6.1.4.1.5923.1.1.1.6",
    "uid",
    "urn:oid:0.9.2342.19200300.100.1.1",
)
EMAIL_ATTR_KEYS: tuple[str, ...] = (
    "mail",
    "email",
    "urn:oid:0.9.2342.19200300.100.1.3",
    "urn:oid:1.2.840.113549.1.9.1",
)
DISPLAY_NAME_ATTR_KEYS: tuple[str, ...] = (
    "displayName",
    "cn",
    "urn:oid:2.16.840.1.113730.3.1.241",
)
GIVEN_NAME_ATTR_KEYS: tuple[str, ...] = (
    "givenName",
    "urn:oid:2.5.4.42",
)
FAMILY_NAME_ATTR_KEYS: tuple[str, ...] = (
    "sn",
    "surname",
    "urn:oid:2.5.4.4",
)


def _coerce_first(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if item:
                text = str(item).strip()
                if text:
                    return text
        return None
    text = str(value).strip()
    return text or None


def _extract_first(attributes: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        candidate = attributes.get(key)
        result = _coerce_first(candidate)
        if result:
            return result
    return None


def _extract_persistent_id(session_info: dict[str, Any] | None) -> str | None:
    if not session_info:
        return None
    name_id = session_info.get("name_id")
    if name_id is None:
        return None
    # pysaml2 NameID objects expose a text attribute with the persistent value.
    text = getattr(name_id, "text", None)
    if text:
        stripped = str(text).strip()
        return stripped or None
    return _coerce_first(name_id)


if pre_user_save is not None:  # pragma: no branch - guarded by import

    @receiver(pre_user_save)
    def sync_user_from_saml(  # type: ignore[misc]
        sender: Any,
        instance: User,
        attributes: dict[str, Any] | None = None,
        created: bool = False,
        request: Any | None = None,
        session_info: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Populate user fields from SAML attributes prior to saving.
        """
        if not getattr(settings, "SAML_LOGIN_ENABLED", False):
            return

        attributes = attributes or {}

        username = _extract_first(attributes, USERNAME_ATTR_KEYS)
        if username:
            # Always prefer the IdP-provided eppn/uid over NameID for consistency.
            instance.username = username

        email = _extract_first(attributes, EMAIL_ATTR_KEYS)
        if email:
            instance.email = email

        display_name = _extract_first(attributes, DISPLAY_NAME_ATTR_KEYS)
        if not display_name:
            given = _extract_first(attributes, GIVEN_NAME_ATTR_KEYS)
            family = _extract_first(attributes, FAMILY_NAME_ATTR_KEYS)
            display_name = " ".join(part for part in (given, family) if part)
        if display_name:
            instance.name = display_name

        persistent_id = _extract_persistent_id(session_info)
        if persistent_id:
            instance.saml_persistent_id = persistent_id

        # Auto-generate ACL agent URI from eppn/email for ACL matching.
        candidate = instance.username
        if instance.email and "@" in instance.email:
            candidate = instance.email
        if candidate and "@" in candidate:
            instance.acl_agent_uri = f"urn:lacos:eppn:{candidate}"


if post_authenticated is not None:  # pragma: no branch - guarded by import

    @receiver(post_authenticated)
    def clear_trusted_signup_flag(  # type: ignore[misc]
        sender: Any,
        user: User,
        request: Any | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Remove trusted signup markers once authentication completes.
        """
        if not getattr(settings, "SAML_LOGIN_ENABLED", False):
            return

        if request is None:
            return

        session = getattr(request, "session", None)
        if session is not None:
            session.pop(TRUSTED_SAML_SESSION_KEY, None)
        setattr(request, "trusted_saml_signup", False)
