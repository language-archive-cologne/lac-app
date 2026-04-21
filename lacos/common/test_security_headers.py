import pytest

from lacos.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_home_page_sets_security_headers(client):
    response = client.get("/")

    assert "Content-Security-Policy" in response.headers
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.django_db
def test_authenticated_htmx_response_is_not_cacheable(client):
    user = UserFactory()
    client.force_login(user)

    response = client.get(
        f"/users/{user.username}/",
        HTTP_HX_REQUEST="true",
    )

    cache_control = response.headers.get("Cache-Control", "")
    assert "no-store" in cache_control
    assert "no-cache" in cache_control
