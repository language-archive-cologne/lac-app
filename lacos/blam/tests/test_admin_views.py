import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from lacos.blam.views.admin_views import (
    ArchivistDashboardView,
    ArchivistMetadataPanelView,
)
from lacos.users.tests.factories import UserFactory


def _ensure_group(name):
    return Group.objects.get_or_create(name=name)[0]


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def archivist(db):
    user = UserFactory()
    user.groups.add(_ensure_group("archivists"))
    return user


@pytest.fixture
def staff_user(db):
    return UserFactory(is_staff=True)


@pytest.fixture
def regular_user(db):
    return UserFactory(is_superuser=False, is_staff=False)


@pytest.mark.django_db
class TestArchivistDashboardView:
    def test_archivist_can_access(self, rf, archivist):
        request = rf.get("/blam/dashboard/archivist/")
        request.user = archivist
        response = ArchivistDashboardView.as_view()(request)
        assert response.status_code == 200

    def test_staff_can_access(self, rf, staff_user):
        request = rf.get("/blam/dashboard/archivist/")
        request.user = staff_user
        response = ArchivistDashboardView.as_view()(request)
        assert response.status_code == 200

    def test_regular_user_denied(self, rf, regular_user):
        request = rf.get("/blam/dashboard/archivist/")
        request.user = regular_user
        with pytest.raises(PermissionDenied):
            ArchivistDashboardView.as_view()(request)

    def test_anonymous_user_redirected(self, rf):
        request = rf.get("/blam/dashboard/archivist/")
        request.user = AnonymousUser()
        response = ArchivistDashboardView.as_view()(request)
        assert response.status_code == 302


@pytest.mark.django_db
class TestArchivistMetadataPanelView:
    def test_archivist_can_access(self, rf, archivist):
        request = rf.get("/blam/dashboard/archivist/metadata-panel/")
        request.user = archivist
        response = ArchivistMetadataPanelView.as_view()(request)
        assert response.status_code == 200

    def test_regular_user_denied(self, rf, regular_user):
        request = rf.get("/blam/dashboard/archivist/metadata-panel/")
        request.user = regular_user
        with pytest.raises(PermissionDenied):
            ArchivistMetadataPanelView.as_view()(request)
