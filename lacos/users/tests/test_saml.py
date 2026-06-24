from __future__ import annotations

import html
import logging
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import resolve
from django.urls import reverse

from lacos.users.adapters import TRUSTED_SAML_SESSION_KEY
from lacos.users.backends import LacosSaml2Backend
from lacos.users.models import SamlCountry
from lacos.users.models import SamlIdp
from lacos.users.models import User
from lacos.users.saml import sync_user_from_saml
from lacos.users.saml_views import LacosAssertionConsumerServiceView
from lacos.users.saml_views import LacosLoginView
from lacos.users.saml_views import LacosMetadataView
from lacos.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def enable_saml(settings):
    settings.SAML_LOGIN_ENABLED = True
    settings.SAML_USE_NAME_ID_AS_USERNAME = False
    settings.SAML_DJANGO_USER_MAIN_ATTRIBUTE = "username"
    settings.SAML_ATTRIBUTE_MAPPING = {
        "eduPersonPrincipalName": ("username",),
    }


def _build_session_info(name_id: str, attributes: dict[str, list[str]]) -> dict:
    return {
        "issuer": "https://idp.test/shibboleth",
        "name_id": SimpleNamespace(text=name_id),
        "ava": attributes,
    }


def test_sync_user_from_saml_keeps_only_required_identifier():
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
    assert user.email == ""
    assert user.name == ""
    assert user.saml_persistent_id in (None, "")
    assert user.acl_agent_uri == "urn:lacos:eppn:user123"


def test_sync_user_from_saml_ignores_optional_profile_attributes():
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

    assert user.username == "combined"
    assert user.name == ""
    assert user.email == ""
    assert user.saml_persistent_id in (None, "")


@pytest.mark.django_db
def test_backend_creates_user_with_required_identifier_only(settings):
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
    assert user.email == ""
    assert user.name == ""
    assert user.saml_persistent_id in (None, "")
    assert user.acl_agent_uri == "urn:lacos:eppn:backend-user"


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
    assert user.username == "existing-user"
    assert user.email == "old@example.com"
    assert user.name == "Old Name"
    assert user.saml_persistent_id == "urn:persistent:link-me"


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
    assert user.email == ""
    assert user.name == ""
    assert user.saml_persistent_id in (None, "")
    assert user.acl_agent_uri == "urn:lacos:eppn:eppn-user"


def test_saml_acs_view_skips_subject_storage_without_name_id(
    monkeypatch,
    caplog,
    settings,
):
    authenticated_user = User(username="pah95jk@uni-wuerzburg.de")
    request = RequestFactory().post("/saml2/acs/")
    request.saml_session = {}
    view = LacosAssertionConsumerServiceView()
    view.request = request
    post_login_calls = []
    customize_calls = []
    subject_ids = []

    monkeypatch.setattr(
        "lacos.users.saml_views.auth.authenticate",
        lambda **_kwargs: authenticated_user,
    )
    monkeypatch.setattr(
        "lacos.users.saml_views.auth.login",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "lacos.users.saml_views._set_subject_id",
        lambda _session, subject_id: subject_ids.append(subject_id),
    )
    monkeypatch.setattr(
        view,
        "post_login_hook",
        lambda *_args: post_login_calls.append(True),
    )
    monkeypatch.setattr(
        view,
        "customize_session",
        lambda *_args: customize_calls.append(True),
    )
    session_info = {
        "issuer": "https://shibboleth-idp.uni-wuerzburg.de/idp/shibboleth",
        "name_id": None,
        "ava": {"eduPersonPrincipalName": ["pah95jk@uni-wuerzburg.de"]},
    }

    with caplog.at_level(logging.WARNING, logger="lacos.users.saml_views"):
        user = view.authenticate_user(
            request,
            session_info,
            settings.SAML_ATTRIBUTE_MAPPING,
            create_unknown_user=True,
            assertion_info={},
        )

    assert user is authenticated_user
    assert subject_ids == []
    assert post_login_calls == [True]
    assert customize_calls == [True]
    assert request.saml_session == {}
    assert "did not include NameID" in caplog.text


def test_saml_acs_view_stores_subject_id_when_name_id_exists(monkeypatch, settings):
    authenticated_user = User(username="user@example.org")
    name_id = SimpleNamespace(text="persistent-subject")
    request = RequestFactory().post("/saml2/acs/")
    request.saml_session = {}
    view = LacosAssertionConsumerServiceView()
    view.request = request
    subject_ids = []

    monkeypatch.setattr(
        "lacos.users.saml_views.auth.authenticate",
        lambda **_kwargs: authenticated_user,
    )
    monkeypatch.setattr(
        "lacos.users.saml_views.auth.login",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "lacos.users.saml_views._set_subject_id",
        lambda _session, subject_id: subject_ids.append(subject_id),
    )
    monkeypatch.setattr(view, "post_login_hook", lambda *_args: None)
    monkeypatch.setattr(view, "customize_session", lambda *_args: None)
    session_info = {
        "issuer": "https://idp.example.org/idp/shibboleth",
        "name_id": name_id,
        "ava": {"eduPersonPrincipalName": ["user@example.org"]},
    }

    user = view.authenticate_user(
        request,
        session_info,
        settings.SAML_ATTRIBUTE_MAPPING,
        create_unknown_user=True,
        assertion_info={},
    )

    assert user is authenticated_user
    assert subject_ids == [name_id]


def test_saml_acs_view_raises_permission_denied_when_authentication_fails(
    monkeypatch,
    settings,
):
    request = RequestFactory().post("/saml2/acs/")
    request.saml_session = {}
    view = LacosAssertionConsumerServiceView()
    view.request = request

    monkeypatch.setattr(
        "lacos.users.saml_views.auth.authenticate",
        lambda **_kwargs: None,
    )

    with pytest.raises(PermissionDenied):
        view.authenticate_user(
            request,
            {
                "issuer": "https://idp.example.org/idp/shibboleth",
                "name_id": None,
                "ava": {},
            },
            settings.SAML_ATTRIBUTE_MAPPING,
            create_unknown_user=True,
            assertion_info={},
        )


def test_saml_acs_auth_failure_warning_does_not_log_full_session_info(
    monkeypatch,
    caplog,
    settings,
):
    request = RequestFactory().post("/saml2/acs/")
    request.saml_session = {}
    view = LacosAssertionConsumerServiceView()
    view.request = request
    session_info = {
        "issuer": "https://idp.ed.ac.uk/shibboleth",
        "name_id": None,
        "ava": {"eduPersonPrincipalName": ["alice@ed.ac.uk"]},
    }

    monkeypatch.setattr(
        "lacos.users.saml_views.auth.authenticate",
        lambda **_kwargs: None,
    )

    with (
        caplog.at_level(logging.WARNING, logger="lacos.users.saml_views"),
        pytest.raises(PermissionDenied),
    ):
        view.authenticate_user(
            request,
            session_info,
            settings.SAML_ATTRIBUTE_MAPPING,
            create_unknown_user=True,
            assertion_info={},
        )

    assert "Could not authenticate user received in SAML Assertion." in caplog.text
    assert "alice@ed.ac.uk" not in caplog.text
    assert "eduPersonPrincipalName" not in caplog.text


def test_saml2_acs_route_uses_lacos_view():
    match = resolve("/saml2/acs/")

    assert match.func.view_class is LacosAssertionConsumerServiceView


def test_saml2_login_route_uses_lacos_view():
    match = resolve("/saml2/login/")

    assert match.func.view_class is LacosLoginView


def test_saml2_metadata_route_uses_lacos_view():
    match = resolve("/saml2/metadata/")

    assert match.func.view_class is LacosMetadataView


def test_saml_acs_failure_logs_sanitized_session_info(caplog):
    request = RequestFactory().post(
        "/saml2/acs/",
        {
            "SAMLResponse": "raw-secret-assertion",
            "RelayState": "/collections/?token=secret",
        },
        HTTP_USER_AGENT="Mozilla/5.0 Example",
        HTTP_X_FORWARDED_FOR="198.51.100.10, 10.0.0.1",
    )
    view = LacosAssertionConsumerServiceView()
    session_info = {
        "issuer": "https://idp.ed.ac.uk/shibboleth",
        "name_id": None,
        "ava": {
            "eduPersonPrincipalName": ["alice@ed.ac.uk"],
            "mail": ["alice@example.org"],
        },
    }

    with caplog.at_level(logging.WARNING, logger="lacos.users.saml_views"):
        response = view.handle_acs_failure(
            request,
            exception=PermissionDenied("No user could be authenticated."),
            status=HTTPStatus.FORBIDDEN,
            session_info=session_info,
        )

    assert response.status_code == HTTPStatus.FORBIDDEN
    record = next(
        record for record in caplog.records if record.message == "SAML ACS failure"
    )
    assert record.saml_failure_exception_type == "PermissionDenied"
    assert record.saml_failure_status == HTTPStatus.FORBIDDEN
    assert record.saml_failure_issuer == "https://idp.ed.ac.uk/shibboleth"
    assert record.saml_failure_name_id_present is False
    assert record.saml_failure_attribute_names == ["eduPersonPrincipalName", "mail"]
    assert record.saml_failure_has_eppn is True
    assert record.saml_failure_eppn_scope == "ed.ac.uk"
    assert record.saml_failure_has_saml_response is True
    assert record.saml_failure_relay_state == "/collections/"
    assert record.saml_failure_remote_addr == "198.51.100.10"
    assert record.saml_failure_user_agent == "Mozilla/5.0 Example"
    assert "raw-secret-assertion" not in caplog.text
    assert "alice@ed.ac.uk" not in caplog.text


@pytest.mark.django_db
def test_saml_acs_failure_renders_friendly_error_page_and_logs_failure(
    client,
    caplog,
):
    raw_saml_response = "not-a-valid-saml-response"

    with caplog.at_level(logging.WARNING, logger="lacos.users.saml_views"):
        response = client.post(
            "/saml2/acs/",
            {
                "SAMLResponse": raw_saml_response,
                "RelayState": "/private/?token=secret",
            },
            HTTP_USER_AGENT="SAML test browser",
            REMOTE_ADDR="203.0.113.15",
        )

    record = next(
        record for record in caplog.records if record.message == "SAML ACS failure"
    )
    assert record.saml_failure_has_saml_response is True
    assert record.saml_failure_relay_state == "/private/"
    assert record.saml_failure_remote_addr == "203.0.113.15"
    assert record.saml_failure_user_agent == "SAML test browser"
    assert raw_saml_response not in caplog.text

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "djangosaml2/login_error.html" in [
        template.name for template in response.templates
    ]
    content = response.content.decode()
    assert "Institutional Login Failed" in content
    assert "not your fault" in content
    assert "lac-helpdesk@uni-koeln.de" in content


@pytest.mark.django_db
def test_saml_login_view_sets_session_marker(client, settings):
    settings.SAML_LOGIN_ENABLED = True
    response = client.get(reverse("users:saml_login"))

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"].endswith("/saml2/login/")
    session = client.session
    assert session.get(TRUSTED_SAML_SESSION_KEY) is True


@pytest.mark.django_db
def test_saml_login_view_preserves_selected_idp(client, settings):
    settings.SAML_LOGIN_ENABLED = True

    response = client.get(
        reverse("users:saml_login"),
        {"idp": "https://idp.example.org/idp/shibboleth"},
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == (
        "/saml2/login/?idp=https%3A%2F%2Fidp.example.org%2Fidp%2Fshibboleth"
    )
    session = client.session
    assert session.get(TRUSTED_SAML_SESSION_KEY) is True


@pytest.mark.django_db
def test_saml_login_view_ignores_selected_idp_when_direct_selection_disabled(
    client,
    settings,
):
    settings.SAML_LOGIN_ENABLED = True
    settings.SAML_DIRECT_IDP_SELECTION_ENABLED = False

    response = client.get(
        reverse("users:saml_login"),
        {
            "idp": "https://idp.example.org/idp/shibboleth",
            "next": "/collections/",
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == "/saml2/login/?next=%2Fcollections%2F"


@pytest.mark.django_db
def test_saml_login_view_preserves_internal_next(client, settings):
    settings.SAML_LOGIN_ENABLED = True

    response = client.get(reverse("users:saml_login"), {"next": "/collections/"})

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == "/saml2/login/?next=%2Fcollections%2F"


@pytest.mark.django_db
def test_saml_login_view_strips_external_next(client, settings):
    settings.SAML_LOGIN_ENABLED = True

    response = client.get(reverse("users:saml_login"), {"next": "https://evil.example/phish"})

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == "/saml2/login/"


@pytest.mark.django_db
def test_saml2_login_redirects_to_discovery_service(client, settings):
    disco_url = "https://wayf.aai.dfn.de/DFN-AAI/wayf"
    settings.SAML2_DISCO_URL = disco_url

    response = client.get("/saml2/login/")

    assert response.status_code == HTTPStatus.FOUND
    location = response.headers["Location"]
    assert location.startswith(disco_url)


@pytest.mark.django_db
def test_saml2_login_accepts_clarin_entity_id_return_parameter(client, settings):
    settings.SAML2_DISCO_URL = "https://discovery.clarin.eu/feed/edugain"
    selected_idp = "https://login.uni-koeln.de/idp/shibboleth"

    response = client.get(
        "/saml2/login/",
        {
            "entityID": selected_idp,
            "next": "/users/~redirect/",
            "returnIDParam": "idp",
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.headers["Location"] == (
        "/saml2/login/?next=%2Fusers%2F~redirect%2F"
        "&idp=https%3A%2F%2Flogin.uni-koeln.de%2Fidp%2Fshibboleth"
    )


@pytest.mark.django_db
def test_saml_discovery_view_links_to_external_discovery_handoff(client):
    response = client.get(reverse("users:saml_discovery"), {"next": "/target/"})

    assert response.status_code == HTTPStatus.OK
    rendered = html.unescape(response.content.decode())
    assert "Continue with CLARIN Discovery" in rendered
    assert 'href="/users/login/saml/?next=/target/"' in rendered
    assert "Choose an institution directly" not in rendered
    assert "idp-search" not in rendered
    assert "country-select" not in rendered
    assert "saml/discover/idps" not in rendered


@pytest.mark.django_db
def test_saml_discovery_view_hides_direct_idp_selection_when_disabled(
    client,
    settings,
):
    settings.SAML_DIRECT_IDP_SELECTION_ENABLED = False

    response = client.get(reverse("users:saml_discovery"), {"next": "/target/"})

    assert response.status_code == HTTPStatus.OK
    rendered = html.unescape(response.content.decode())
    assert "Continue with CLARIN Discovery" in rendered
    assert 'href="/users/login/saml/?next=/target/"' in rendered
    assert "Sign in with credentials" in rendered
    assert "Choose an institution directly" not in rendered
    assert "idp-search" not in rendered
    assert "country-select" not in rendered
    assert "saml/discover/idps" not in rendered


@pytest.mark.django_db
def test_saml_discovery_idp_list_routes_via_trusted_login_view(client, settings):
    settings.SAML_LOGIN_ENABLED = True
    country = SamlCountry.objects.create(code="DE", name="Germany")
    SamlIdp.objects.create(
        entity_id="https://idp.example.org/idp/shibboleth",
        display_name="Example University",
        logo="https://idp.example.org/logo.png",
        country=country,
    )

    response = client.get(
        reverse("users:saml_discovery_idp_list"),
        {"search": "Example", "next": "/target/"},
    )

    assert response.status_code == HTTPStatus.OK
    rendered = html.unescape(response.content.decode())
    assert reverse("users:saml_login") in rendered
    assert 'href="/users/login/saml/?idp=' in rendered
    assert "idp.example.org" in rendered
    assert "next=" in rendered
    assert "<img" not in rendered
    assert "<svg" not in rendered
    assert "https://idp.example.org/logo.png" not in rendered
    assert "onerror=" not in rendered
    assert reverse("saml2_login") not in rendered


@pytest.mark.django_db
def test_saml_discovery_idp_list_404s_when_direct_selection_disabled(
    client,
    settings,
):
    settings.SAML_DIRECT_IDP_SELECTION_ENABLED = False

    response = client.get(
        reverse("users:saml_discovery_idp_list"),
        {"search": "CLARIN"},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND
