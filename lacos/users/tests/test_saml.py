from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.urls import reverse

from lacos.users.adapters import TRUSTED_SAML_SESSION_KEY
from lacos.users.backends import LacosSaml2Backend
from lacos.users.models import User
from lacos.users.saml import sync_user_from_saml
from lacos.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def enable_saml(settings):
    settings.SAML_LOGIN_ENABLED = True
    settings.SAML_USE_NAME_ID_AS_USERNAME = False
    settings.SAML_DJANGO_USER_MAIN_ATTRIBUTE = "username"
    settings.SAML_ATTRIBUTE_MAPPING = {
        "eduPersonPrincipalName": ("username",),
        "mail": ("email",),
        "displayName": ("name",),
    }


def _build_session_info(name_id: str, attributes: dict[str, list[str]]) -> dict:
    return {
        "issuer": "https://idp.test/shibboleth",
        "name_id": SimpleNamespace(text=name_id),
        "ava": attributes,
    }


def test_sync_user_from_saml_populates_fields():
    user = User()
    attributes = {
        "eduPersonPrincipalName": ["user123"],
        "mail": ["user@example.com"],
        "displayName": ["Test User"],
    }
    session_info = {"name_id": SimpleNamespace(text="persistent-id-123")}

    sync_user_from_saml(
        sender=None,
        instance=user,
        attributes=attributes,
        created=True,
        session_info=session_info,
    )

    assert user.username == "user123"
    assert user.email == "user@example.com"
    assert user.name == "Test User"
    assert user.saml_persistent_id == "persistent-id-123"


def test_sync_user_from_saml_combines_given_and_family_names():
    user = User(name="")
    attributes = {
        "eduPersonPrincipalName": ["combined"],
        "mail": ["combined@example.com"],
        "givenName": ["Alice"],
        "sn": ["Example"],
    }
    session_info = {"name_id": SimpleNamespace(text="persistent-xyz")}

    sync_user_from_saml(
        sender=None,
        instance=user,
        attributes=attributes,
        created=True,
        session_info=session_info,
    )

    assert user.name == "Alice Example"


@pytest.mark.django_db
def test_backend_creates_user_with_persistent_identifier(settings):
    backend = LacosSaml2Backend()
    attributes = {
        "eduPersonPrincipalName": ["backend-user"],
        "mail": ["backend@example.com"],
        "displayName": ["Backend User"],
    }
    session_info = _build_session_info("urn:persistent:abc123", attributes)

    user = backend.authenticate(
        request=None,
        session_info=session_info,
        attribute_mapping=settings.SAML_ATTRIBUTE_MAPPING,
        create_unknown_user=True,
    )

    assert isinstance(user, User)
    assert user.username == "backend-user"
    assert user.email == "backend@example.com"
    assert user.name == "Backend User"
    assert user.saml_persistent_id == "urn:persistent:abc123"


@pytest.mark.django_db
def test_backend_links_existing_user_by_username(settings):
    existing = UserFactory(
        username="existing-user",
        email="old@example.com",
        name="Old Name",
        saml_persistent_id="urn:persistent:link-me",
    )
    backend = LacosSaml2Backend()
    attributes = {
        "eduPersonPrincipalName": ["existing-user"],
        "mail": ["updated@example.com"],
        "displayName": ["Updated Name"],
    }
    session_info = _build_session_info("urn:persistent:link-me", attributes)

    user = backend.authenticate(
        request=None,
        session_info=session_info,
        attribute_mapping=settings.SAML_ATTRIBUTE_MAPPING,
        create_unknown_user=True,
    )

    assert user.pk == existing.pk
    user.refresh_from_db()
    assert user.email == "updated@example.com"
    assert user.name == "Updated Name"
    assert user.username == "existing-user"


@pytest.mark.django_db
def test_backend_creates_user_without_name_id_when_using_eppn(settings):
    backend = LacosSaml2Backend()
    attributes = {
        "eduPersonPrincipalName": ["eppn-user"],
        "mail": ["eppn@example.com"],
        "displayName": ["Eppn User"],
    }
    session_info = {
        "issuer": "https://idp.test/shibboleth",
        "name_id": None,
        "ava": attributes,
    }

    user = backend.authenticate(
        request=None,
        session_info=session_info,
        attribute_mapping=settings.SAML_ATTRIBUTE_MAPPING,
        create_unknown_user=True,
    )

    assert isinstance(user, User)
    assert user.username == "eppn-user"
    assert user.saml_persistent_id in (None, "")


@pytest.mark.django_db
def test_saml_login_view_sets_session_marker(client, settings):
    settings.SAML_LOGIN_ENABLED = True
    response = client.get(reverse("users:saml_login"))

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/saml2/login/")
    session = client.session
    assert session.get(TRUSTED_SAML_SESSION_KEY) is True


@pytest.mark.django_db
def test_saml2_login_redirects_to_discovery_service(client, settings):
    disco_url = "https://wayf.aai.dfn.de/DFN-AAI/wayf"
    settings.SAML2_DISCO_URL = disco_url

    response = client.get("/saml2/login/")

    assert response.status_code == 302
    location = response.headers["Location"]
    assert location.startswith(disco_url)
