from __future__ import annotations

import typing

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.http import HttpRequest

if typing.TYPE_CHECKING:
    from allauth.socialaccount.models import SocialLogin

    from lacos.users.models import User


TRUSTED_SAML_SESSION_KEY = "users.saml_trusted_signup"


def _is_trusted_auto_provision(request: HttpRequest | None) -> bool:
    if request is None:
        return False

    if getattr(request, "trusted_saml_signup", False):
        return True

    try:
        return bool(request.session.get(TRUSTED_SAML_SESSION_KEY))
    except AttributeError:
        return False


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        if _is_trusted_auto_provision(request):
            return True
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
    ) -> bool:
        if _is_trusted_auto_provision(request):
            return True
        return getattr(settings, "ACCOUNT_ALLOW_REGISTRATION", True)

    def populate_user(
        self,
        request: HttpRequest,
        sociallogin: SocialLogin,
        data: dict[str, typing.Any],
    ) -> User:
        """
        Populates user information from social provider info.

        See: https://docs.allauth.org/en/latest/socialaccount/advanced.html#creating-and-populating-user-instances
        """
        user = super().populate_user(request, sociallogin, data)
        if not user.name:
            if name := data.get("name"):
                user.name = name
            elif first_name := data.get("first_name"):
                user.name = first_name
                if last_name := data.get("last_name"):
                    user.name += f" {last_name}"
        return user
