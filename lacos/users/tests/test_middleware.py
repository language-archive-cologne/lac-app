from urllib.parse import quote

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from lacos.users.middleware import PrivilegedMFAEnforcementMiddleware
from lacos.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_privileged_mfa_middleware_redirects_staff_without_mfa(settings):
    request = RequestFactory().get("/admin/")
    request.user = UserFactory(is_staff=True)

    response = PrivilegedMFAEnforcementMiddleware(lambda _request: HttpResponse("ok"))(request)

    assert response.status_code == 302
    assert response.url == f"{reverse('mfa_index')}?next={quote('/admin/', safe='')}"


@pytest.mark.django_db
def test_privileged_mfa_middleware_sets_htmx_redirect_for_staff_without_mfa():
    request = RequestFactory().get("/storage/dashboard/", HTTP_HX_REQUEST="true")
    request.user = UserFactory(is_staff=True)

    response = PrivilegedMFAEnforcementMiddleware(lambda _request: HttpResponse("ok"))(request)

    assert response.status_code == 403
    assert response["HX-Redirect"] == f"{reverse('mfa_index')}?next={quote('/storage/dashboard/', safe='')}"
