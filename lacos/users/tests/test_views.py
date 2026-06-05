from http import HTTPStatus

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import reverse

from lacos.users.models import User
from lacos.users.tests.factories import UserFactory
from lacos.users.views import UserRedirectView
from lacos.users.views import user_detail_view

pytestmark = pytest.mark.django_db


class TestDisabledAccountManagementView:
    def test_profile_update_is_not_available(self, client, user: User):
        client.force_login(user)
        response = client.get(reverse("users:update"))

        assert response.status_code == HTTPStatus.NOT_FOUND

    def test_profile_update_does_not_change_name(self, client, user: User):
        client.force_login(user)
        response = client.post(reverse("users:update"), data={"name": "Changed"})

        user.refresh_from_db()
        assert response.status_code == HTTPStatus.NOT_FOUND
        assert user.name != "Changed"

    def test_allauth_email_management_is_not_available(self, client, user: User):
        client.force_login(user)
        response = client.get(reverse("account_email"))

        assert response.status_code == HTTPStatus.NOT_FOUND

    @pytest.mark.parametrize(
        "path",
        [
            "/accounts/2fa/",
            "/accounts/2fa/totp/activate/",
            "/accounts/2fa/recovery-codes/",
        ],
    )
    def test_allauth_mfa_management_is_not_available(self, client, user: User, path):
        client.force_login(user)
        response = client.get(path)

        assert response.status_code == HTTPStatus.NOT_FOUND


class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory):
        view = UserRedirectView()
        request = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == reverse("home")


class TestUserDetailView:
    def test_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = user
        response = user_detail_view(request, username=user.username)

        assert response.status_code == HTTPStatus.OK

    def test_self_service_account_links_are_hidden(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = user
        response = user_detail_view(request, username=user.username)
        response.render()
        content = response.content.decode()

        assert reverse("users:update") not in content
        assert reverse("account_email") not in content
        assert "My Info" not in content
        assert "E-Mail" not in content
        assert "MFA" not in content

    def test_profile_shows_read_only_username(self, rf: RequestFactory):
        user = UserFactory(name="Hidden Display Name")
        request = rf.get("/fake-url/")
        request.user = user
        response = user_detail_view(request, username=user.username)
        response.render()
        content = response.content.decode()

        assert "Profile" in content
        assert "Read-only" in content
        assert "Username" in content
        assert user.username in content
        assert "Display name" not in content
        assert user.name not in content

    def test_other_user_is_hidden(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = UserFactory()

        with pytest.raises(Http404):
            user_detail_view(request, username=user.username)

    def test_not_authenticated(self, user: User, rf: RequestFactory):
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, username=user.username)
        login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next=/fake-url/"
