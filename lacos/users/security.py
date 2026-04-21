from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

from lacos.storage.permissions import COLLECTION_MANAGER_GROUP_NAME


PRIVILEGED_PATH_PREFIXES = (
    "/storage/",
    "/dbadmin/",
)


def user_requires_mfa(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(
        user.is_staff
        or user.is_superuser
        or user.groups.filter(name=COLLECTION_MANAGER_GROUP_NAME).exists()
    )


def user_has_mfa_authenticator(user) -> bool:
    if not user_requires_mfa(user):
        return True

    from allauth.mfa.models import Authenticator

    return Authenticator.objects.filter(user=user).exists()


def privileged_path_prefixes() -> tuple[str, ...]:
    admin_path = f"/{str(settings.ADMIN_URL).strip('/')}/"
    return (admin_path, *PRIVILEGED_PATH_PREFIXES)


def build_mfa_redirect_url(request) -> str:
    query_string = urlencode({"next": request.get_full_path()})
    return f"{reverse('mfa_index')}?{query_string}"
