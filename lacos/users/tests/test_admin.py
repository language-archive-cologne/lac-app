import contextlib
from http import HTTPStatus
from importlib import reload

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from lacos.users.admin import (
    AuthSourceFilter,
    is_eppn_saml,
    is_legacy_saml,
    user_has_saml_identity,
)
from lacos.users.models import User


class TestUserAdmin:
    @pytest.fixture
    def admin_client(self, client, admin_user):
        client.force_login(admin_user)
        return client

    def test_changelist(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_search(self, admin_client):
        url = reverse("admin:users_user_changelist")
        response = admin_client.get(url, data={"q": "test"})
        assert response.status_code == HTTPStatus.OK

    def test_add(self, admin_client):
        url = reverse("admin:users_user_add")
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

        response = admin_client.post(
            url,
            data={
                "username": "test",
                "password1": "My_R@ndom-P@ssw0rd",
                "password2": "My_R@ndom-P@ssw0rd",
            },
        )
        assert response.status_code == HTTPStatus.FOUND
        assert User.objects.filter(username="test").exists()

    def test_view_user(self, admin_client):
        user = User.objects.get(username="admin")
        url = reverse("admin:users_user_change", kwargs={"object_id": user.pk})
        response = admin_client.get(url)
        assert response.status_code == HTTPStatus.OK

    def test_auth_source_uses_eppn_acl_uri(self):
        user_admin = admin.site._registry[User]
        saml_user = User(
            username="sievert@uni-wuppertal.de",
            acl_agent_uri="urn:lacos:eppn:sievert@uni-wuppertal.de",
        )
        legacy_saml_user = User(username="legacy-saml", saml_persistent_id="legacy-id")
        combined_user = User(
            username="combined",
            saml_persistent_id="legacy-id-2",
            acl_agent_uri="urn:lacos:eppn:combined@uni-koeln.de",
        )
        local_user = User(username="local-user")

        # Canonical EPPN path
        assert is_eppn_saml(saml_user) is True
        assert is_legacy_saml(saml_user) is False
        assert user_has_saml_identity(saml_user) is True
        assert user_admin.auth_source(saml_user) == "SAML"

        # Legacy-only path
        assert is_eppn_saml(legacy_saml_user) is False
        assert is_legacy_saml(legacy_saml_user) is True
        assert user_has_saml_identity(legacy_saml_user) is True
        assert user_admin.auth_source(legacy_saml_user) == "SAML"

        # Both flags set — still SAML, both predicates True
        assert is_eppn_saml(combined_user) is True
        assert is_legacy_saml(combined_user) is True
        assert user_has_saml_identity(combined_user) is True
        assert user_admin.auth_source(combined_user) == "SAML"

        # Neither flag set
        assert is_eppn_saml(local_user) is False
        assert is_legacy_saml(local_user) is False
        assert user_has_saml_identity(local_user) is False
        assert user_admin.auth_source(local_user) == "Local"

    @pytest.mark.django_db
    def test_auth_source_filter_uses_eppn_acl_uri(self):
        saml_user = User.objects.create_user(
            username="sievert@uni-wuppertal.de",
            acl_agent_uri="urn:lacos:eppn:sievert@uni-wuppertal.de",
        )
        legacy_saml_user = User.objects.create_user(
            username="legacy-saml",
            saml_persistent_id="legacy-id",
        )
        combined_user = User.objects.create_user(
            username="combined",
            saml_persistent_id="legacy-id-2",
            acl_agent_uri="urn:lacos:eppn:combined@uni-koeln.de",
        )
        local_user = User.objects.create_user(username="local-user")
        saml_filter = AuthSourceFilter.__new__(AuthSourceFilter)
        saml_filter.used_parameters = {"auth_source": "saml"}
        local_filter = AuthSourceFilter.__new__(AuthSourceFilter)
        local_filter.used_parameters = {"auth_source": "local"}

        assert list(saml_filter.queryset(None, User.objects.order_by("username"))) == [
            combined_user,
            legacy_saml_user,
            saml_user,
        ]
        assert list(local_filter.queryset(None, User.objects.order_by("username"))) == [
            local_user,
        ]

    @pytest.fixture
    def _force_allauth(self, settings):
        settings.DJANGO_ADMIN_FORCE_ALLAUTH = True
        # Reload the admin module to apply the setting change
        import lacos.users.admin as users_admin

        with contextlib.suppress(admin.sites.AlreadyRegistered):  # type: ignore[attr-defined]
            reload(users_admin)

    @pytest.mark.django_db
    @pytest.mark.usefixtures("_force_allauth")
    def test_allauth_login(self, rf, settings):
        request = rf.get("/fake-url")
        request.user = AnonymousUser()
        response = admin.site.login(request)

        # The `admin` login view should redirect to the `allauth` login view
        target_url = reverse(settings.LOGIN_URL) + "?next=" + request.path
        assertRedirects(response, target_url, fetch_redirect_response=False)
