"""
Custom SAML backend integrations.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from django.conf import settings
from djangosaml2.backends import Saml2Backend as _Saml2Backend

logger = logging.getLogger(__name__)


class LacosSaml2Backend(_Saml2Backend):
    """
    Extend the stock backend so existing users keep immutable fields.
    """

    immutable_fields: tuple[str, ...] = ("username",)

    def _filter_attribute_mapping(
        self,
        attribute_mapping: Mapping[str, tuple[str, ...]] | None,
        user: Any,
    ) -> Mapping[str, tuple[str, ...]] | None:
        if attribute_mapping is None:
            return None

        if getattr(user, "pk", None) is None:
            return attribute_mapping

        filtered: dict[str, tuple[str, ...]] = {}
        for saml_attr, django_fields in attribute_mapping.items():
            filtered_fields = tuple(
                field for field in django_fields if field not in self.immutable_fields
            )
            if filtered_fields:
                filtered[saml_attr] = filtered_fields
        return filtered

    def _update_user(
        self,
        user: Any,
        attributes: dict[str, Any],
        attribute_mapping: Mapping[str, tuple[str, ...]] | None,
        force_save: bool = False,
    ) -> Any:
        filtered_mapping = self._filter_attribute_mapping(attribute_mapping, user)
        return super()._update_user(user, attributes, filtered_mapping, force_save)

    def authenticate(  # type: ignore[override]
        self,
        request: Any | None = None,
        session_info: dict[str, Any] | None = None,
        attribute_mapping: Mapping[str, tuple[str, ...]] | None = None,
        create_unknown_user: bool = False,
        **kwargs: Any,
    ) -> Any:
        if getattr(settings, "SAML_LOGIN_ENABLED", False):
            self._log_lookup_attribute(session_info, attribute_mapping)
        user = super().authenticate(
            request=request,
            session_info=session_info,
            attribute_mapping=attribute_mapping,
            create_unknown_user=create_unknown_user,
            **kwargs,
        )
        if user is not None:
            self._sync_persistent_id(user, session_info)
        return user

    @staticmethod
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

    def _sync_persistent_id(
        self,
        user: Any,
        session_info: dict[str, Any] | None,
    ) -> None:
        if session_info is None:
            return

        name_id = session_info.get("name_id")
        if name_id is None:
            return

        persistent_id = self._coerce_first(getattr(name_id, "text", None)) or self._coerce_first(name_id)
        if not persistent_id or getattr(user, "saml_persistent_id", None) == persistent_id:
            return

        user.saml_persistent_id = persistent_id
        user.save(update_fields=["saml_persistent_id"])

    def _log_lookup_attribute(
        self,
        session_info: dict[str, Any] | None,
        attribute_mapping: Mapping[str, tuple[str, ...]] | None,
    ) -> None:
        main_attr = str(
            getattr(settings, "SAML_DJANGO_USER_MAIN_ATTRIBUTE", "")
        ).strip()
        if not main_attr:
            return

        attributes = {}
        if session_info:
            attributes = session_info.get("ava") or {}

        mapping = attribute_mapping or getattr(settings, "SAML_ATTRIBUTE_MAPPING", {})
        saml_attrs = [
            saml_attr
            for saml_attr, fields in mapping.items()
            if main_attr in fields
        ]
        lookup_source = "unknown"
        for saml_attr in saml_attrs:
            value = self._coerce_first(attributes.get(saml_attr))
            if value:
                lookup_source = f"ava:{saml_attr}"
                break
        else:
            if main_attr == "saml_persistent_id":
                lookup_source = "name_id"
            elif saml_attrs:
                lookup_source = f"ava:{saml_attrs[0]} (missing)"

        logger.info(
            "SAML lookup attribute: django_field=%s source=%s",
            main_attr,
            lookup_source,
        )
