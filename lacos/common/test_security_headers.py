import pytest

from lacos.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_home_page_sets_security_headers(client):
    response = client.get("/")

    assert "Content-Security-Policy" in response.headers
    assert "worker-src 'self' blob:" in response.headers["Content-Security-Policy"]
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


@pytest.mark.django_db
def test_csp_allows_configured_map_origins(client, settings):
    settings.EXPLORER_MAP_PMTILES_URL = "http://localhost:9100/lacos-maps/ne.pmtiles"
    settings.EXPLORER_MAP_GLYPHS_URL = "http://localhost:9100/lacos-maps/glyphs"

    response = client.get("/collections/")

    csp = response.headers["Content-Security-Policy"]
    assert "connect-src" in csp
    assert "font-src" in csp
    assert "http://localhost:9100" in csp


@pytest.mark.django_db
def test_csp_allows_configured_static_origin(client, settings):
    settings.STATIC_URL = "https://static.example.test/static/"

    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self' 'unsafe-inline' https://static.example.test" in csp
    assert "style-src 'self' 'unsafe-inline' https://static.example.test" in csp
