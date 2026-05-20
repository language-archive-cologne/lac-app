import pytest
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test import override_settings


@pytest.fixture
def rf():
    return RequestFactory()


@override_settings(DOWNLOAD_PACKAGE_MAX_BYTES=25 * 1024 * 1024)
def test_bundle_download_modal_warns_about_package_size_limit(rf):
    request = rf.get("/")
    request.user = AnonymousUser()

    html = render_to_string(
        "dashboard/partials/bundle_download_modal.html",
        request=request,
    )

    assert "Packages larger than 25 MB cannot be created" in html
    assert "run the generated script for larger downloads" in html
    assert 'id="bundle-download-total-size"' in html
