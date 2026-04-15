import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from lacos.dbadmin.views import (
    DashboardView,
    OverviewStatsView,
    TaskHistoryView,
)
from lacos.users.tests.factories import UserFactory


@pytest.fixture
def superuser(db):
    return UserFactory(is_superuser=True, is_staff=True)


@pytest.fixture
def regular_user(db):
    return UserFactory(is_superuser=False, is_staff=False)


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.mark.django_db
class TestDashboardView:
    def test_superuser_can_access(self, rf, superuser):
        request = rf.get("/dbadmin/")
        request.user = superuser
        response = DashboardView.as_view()(request)
        assert response.status_code == 200

    def test_regular_user_denied(self, rf, regular_user):
        request = rf.get("/dbadmin/")
        request.user = regular_user
        with pytest.raises(PermissionDenied):
            DashboardView.as_view()(request)

    def test_anonymous_user_denied(self, rf):
        from django.contrib.auth.models import AnonymousUser
        request = rf.get("/dbadmin/")
        request.user = AnonymousUser()
        response = DashboardView.as_view()(request)
        assert response.status_code == 302


@pytest.mark.django_db
class TestOverviewStatsView:
    def test_returns_html(self, rf, superuser):
        request = rf.get("/dbadmin/stats/")
        request.user = superuser
        response = OverviewStatsView.as_view()(request)
        assert response.status_code == 200


@pytest.mark.django_db
class TestTaskHistoryView:
    def test_returns_html(self, rf, superuser):
        request = rf.get("/dbadmin/tasks/history/")
        request.user = superuser
        response = TaskHistoryView.as_view()(request)
        assert response.status_code == 200

    def test_filters_by_status(self, rf, superuser):
        request = rf.get("/dbadmin/tasks/history/", {"status": "success"})
        request.user = superuser
        response = TaskHistoryView.as_view()(request)
        assert response.status_code == 200
