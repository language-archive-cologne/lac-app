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
    "urn:oid:0.9.2342.19200300.100.1.3",
)
COMMON_NAME_ATTR_KEYS: tuple[str, ...] = (
    "cn",
    "urn:oid:2.5.4.3",
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


def _is_meaningful_common_name(
    common_name: str,
    username: str | None,
    email: str | None,
) -> bool:
    normalized = common_name.casefold()
    ignored_values = {
        value.casefold()
        for value in (username, email)
        if value
    }
    if normalized in ignored_values:
        return False
    return "@" not in common_name


def sync_profile_fields_from_saml(instance: User, attributes: dict[str, Any]) -> set[str]:
    updated_fields: set[str] = set()

    email = _extract_first(attributes, EMAIL_ATTR_KEYS)
    if email and instance.email != email:
        instance.email = email
        updated_fields.add("email")

    common_name = _extract_first(attributes, COMMON_NAME_ATTR_KEYS)
    if common_name and _is_meaningful_common_name(
        common_name,
        instance.username,
        instance.email,
    ):
        if instance.name != common_name:
            instance.name = common_name
            updated_fields.add("name")
    elif instance.name in {instance.username, instance.email}:
        instance.name = ""
        updated_fields.add("name")

    return updated_fields


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

        sync_profile_fields_from_saml(instance, attributes)

        # Keep only the federated identifier required for login and ACL matching.
        if instance.username:
            instance.acl_agent_uri = f"urn:lacos:eppn:{instance.username}"


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
