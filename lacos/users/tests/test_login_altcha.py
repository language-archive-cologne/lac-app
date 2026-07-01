from http import HTTPStatus
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse

from lacos.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_local_login_template_renders_altcha_widget(client):
    response = client.get(f"{reverse('account_login')}?credentials=1")

    assert response.status_code == HTTPStatus.OK
    content = response.content.decode()
    assert "<altcha-widget" in content
    assert 'name="altcha"' in content
    assert reverse("storage:altcha_challenge") in content


def test_local_login_without_altcha_is_rejected_before_verification(client):
    user = UserFactory()
    user.set_password("valid-pass")
    user.save()

    with patch("lacos.users.views.get_altcha_service") as get_service:
        response = client.post(
            reverse("account_login"),
            data={"login": user.username, "password": "valid-pass"},
        )

    assert response.status_code == HTTPStatus.OK
    assert "_auth_user_id" not in client.session
    assert get_service.call_count == 0
    assert len(mail.outbox) == 0
    assert "Please complete the bot verification" in response.content.decode()


def test_local_login_wrong_password_sends_no_admin_email(client):
    user = UserFactory()
    user.set_password("valid-pass")
    user.save()
    service = Mock()
    service.verify_solution_base64.return_value = (True, None)

    with patch("lacos.users.views.get_altcha_service", return_value=service):
        response = client.post(
            reverse("account_login"),
            data={
                "login": user.username,
                "password": "wrong-pass",
                "altcha": "valid-payload",
            },
        )

    assert response.status_code == HTTPStatus.OK
    assert "_auth_user_id" not in client.session
    assert len(mail.outbox) == 0
    service.verify_solution_base64.assert_called_once_with("valid-payload")


def test_local_login_with_valid_altcha_can_authenticate(client):
    user = UserFactory()
    user.set_password("valid-pass")
    user.save()
    service = Mock()
    service.verify_solution_base64.return_value = (True, None)

    with patch("lacos.users.views.get_altcha_service", return_value=service):
        response = client.post(
            reverse("account_login"),
            data={
                "login": user.username,
                "password": "valid-pass",
                "altcha": "valid-payload",
            },
        )

    assert response.status_code == HTTPStatus.FOUND
    assert client.session["_auth_user_id"] == str(user.pk)
    service.verify_solution_base64.assert_called_once_with("valid-payload")
