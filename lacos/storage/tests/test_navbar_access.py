from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from lacos.storage.context_processors import navbar_access
from lacos.users.tests.factories import UserFactory


@pytest.fixture
def rf():
    return RequestFactory()


def _request_for(user, rf):
    request = rf.get("/")
    request.user = user
    request.resolver_match = SimpleNamespace(view_name="home")
    return request


def _ensure_group(name):
    return Group.objects.get_or_create(name=name)[0]


def _render_navbar(request):
    return render_to_string("navbar.html", request=request)


@pytest.mark.django_db
def test_navbar_access_anonymous_user_has_only_public_sections(rf):
    request = _request_for(AnonymousUser(), rf)

    access = navbar_access(request)["NAVBAR_ACCESS"]

    assert access["show_manage_group"] is False
    assert access["show_system_group"] is False
    assert access["show_storage"] is False
    assert access["show_blam"] is False
    assert access["show_acl"] is False
    assert access["show_dbadmin"] is False
    assert access["show_admin"] is False


@pytest.mark.django_db
def test_navbar_access_collection_manager_sees_storage_only(rf):
    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    request = _request_for(user, rf)

    access = navbar_access(request)["NAVBAR_ACCESS"]

    assert access["show_manage_group"] is True
    assert access["show_storage"] is True
    assert access["show_blam"] is False
    assert access["show_acl"] is False
    assert access["show_system_group"] is False


@pytest.mark.django_db
def test_navbar_access_archivist_sees_storage_blam_and_acl(rf):
    user = UserFactory()
    user.groups.add(_ensure_group("archivists"))
    request = _request_for(user, rf)

    access = navbar_access(request)["NAVBAR_ACCESS"]

    assert access["show_manage_group"] is True
    assert access["show_storage"] is True
    assert access["show_blam"] is True
    assert access["show_acl"] is True
    assert access["show_system_group"] is False


@pytest.mark.django_db
def test_navbar_access_staff_sees_blam_and_admin(rf):
    user = UserFactory(is_staff=True)
    request = _request_for(user, rf)

    access = navbar_access(request)["NAVBAR_ACCESS"]

    assert access["show_manage_group"] is True
    assert access["show_storage"] is False
    assert access["show_blam"] is True
    assert access["show_acl"] is False
    assert access["show_system_group"] is True
    assert access["show_dbadmin"] is False
    assert access["show_admin"] is True


@pytest.mark.django_db
def test_navbar_renders_only_storage_for_collection_manager(rf):
    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    request = _request_for(user, rf)

    html = _render_navbar(request)

    assert reverse("storage:archivist_dashboard") in html
    assert reverse("blam:blam_archivist_dashboard") not in html
    assert reverse("storage:acl_admin_dashboard") not in html
    assert reverse("dbadmin:dashboard") not in html
    assert reverse("admin:index") not in html


@pytest.mark.django_db
def test_navbar_renders_acl_for_archivist_non_superuser(rf):
    user = UserFactory()
    user.groups.add(_ensure_group("archivists"))
    request = _request_for(user, rf)

    html = _render_navbar(request)

    assert reverse("storage:archivist_dashboard") in html
    assert reverse("blam:blam_archivist_dashboard") in html
    assert reverse("storage:acl_admin_dashboard") in html
    assert reverse("dbadmin:dashboard") not in html


@pytest.mark.django_db
def test_navbar_renders_blam_and_admin_for_staff(rf):
    user = UserFactory(is_staff=True)
    request = _request_for(user, rf)

    html = _render_navbar(request)

    assert reverse("blam:blam_archivist_dashboard") in html
    assert reverse("admin:index") in html
    assert reverse("storage:archivist_dashboard") not in html
    assert reverse("storage:acl_admin_dashboard") not in html
    assert reverse("dbadmin:dashboard") not in html
