import pytest
from django.urls import NoReverseMatch
from django.urls import resolve
from django.urls import reverse

from lacos.users.models import User


def test_detail(user: User):
    assert (
        reverse("users:detail", kwargs={"username": user.username})
        == f"/users/{user.username}/"
    )
    assert resolve(f"/users/{user.username}/").view_name == "users:detail"


def test_update():
    assert reverse("users:update") == "/users/~update/"
    assert resolve("/users/~update/").view_name == "users:update"


def test_mfa_urls_are_not_registered():
    with pytest.raises(NoReverseMatch):
        reverse("mfa_index")


def test_redirect():
    assert reverse("users:redirect") == "/users/~redirect/"
    assert resolve("/users/~redirect/").view_name == "users:redirect"
