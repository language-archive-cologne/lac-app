"""
Custom SAML backend integrations.
"""

from __future__ import annotations

from typing import Any, Mapping


from djangosaml2.backends import Saml2Backend as _Saml2Backend


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

