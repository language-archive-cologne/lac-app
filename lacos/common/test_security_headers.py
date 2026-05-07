import pytest

from lacos.common.middleware import SecurityHeadersMiddleware
from lacos.common.services.csp import build_csp_sha256, collect_inline_csp_hashes
from lacos.users.tests.factories import UserFactory


@pytest.mark.django_db
def test_home_page_sets_security_headers(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]

    assert "Content-Security-Policy" in response.headers
    assert "worker-src 'self' blob:" in csp
    assert "media-src 'self' blob:" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "style-src-elem 'self' 'unsafe-inline'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp
    assert "'unsafe-hashes'" in csp
    assert "'sha256-" in csp
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"


@pytest.mark.django_db
def test_csp_allows_runtime_style_mutations_without_inline_scripts(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]

    assert "script-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "style-src-elem 'self' 'unsafe-inline'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp


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
def test_csp_allows_configured_storage_browser_origin_for_embeds(client, settings):
    settings.AWS_S3_BROWSER_ENDPOINT_URL = "http://localhost:9100"

    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "frame-src" in csp
    assert "media-src" in csp
    assert "img-src" in csp
    assert "http://localhost:9100" in csp


def test_storage_browser_endpoint_is_available_to_csp(settings):
    assert hasattr(settings, "AWS_S3_BROWSER_ENDPOINT_URL")


@pytest.mark.django_db
def test_csp_allows_storage_api_and_extra_asset_origins_for_media(client, settings):
    settings.AWS_S3_ENDPOINT_URL = "https://rdsp.fds.uni-koeln.de"
    settings.CSP_EXTRA_ASSET_ORIGINS = ["https://media-cdn.example.test/assets"]

    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "media-src" in csp
    assert "media-src 'self' blob:" in csp
    assert "connect-src" in csp
    assert "https://rdsp.fds.uni-koeln.de" in csp
    assert "https://media-cdn.example.test" in csp


@pytest.mark.django_db
def test_csp_allows_configured_saml_form_action_origins(client, settings):
    settings.SAML_METADATA_REFRESH_URL = "https://idp.rrz.uni-koeln.de/idp/shibboleth"
    settings.SAML_FORM_ACTION_ORIGINS = ["https://idp.example.org/saml/sso"]

    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "form-action 'self' https://idp.rrz.uni-koeln.de https://idp.example.org" in csp
    assert "form-action 'self' https:;" not in csp


@pytest.mark.django_db
def test_csp_allows_configured_static_origin(client, settings):
    settings.STATIC_URL = "https://static.example.test/static/"

    response = client.get("/")

    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self' https://static.example.test" in csp
    assert "style-src 'self' 'unsafe-inline' https://static.example.test" in csp


def test_collect_inline_csp_hashes_tracks_inline_scripts_handlers_and_styles():
    document = """
    <html>
      <head>
        <style>.banner { color: red; }</style>
      </head>
      <body onclick="closeModal()" style="display:none">
        <script>window.bootstrapTheme();</script>
      </body>
    </html>
    """

    hashes = collect_inline_csp_hashes(document)

    assert build_csp_sha256("window.bootstrapTheme();") in hashes.script_hashes
    assert build_csp_sha256("closeModal()") in hashes.script_hashes
    assert build_csp_sha256(".banner { color: red; }") in hashes.style_hashes
    assert build_csp_sha256("display:none") in hashes.style_hashes
    assert hashes.has_script_attribute_hashes is True
    assert hashes.has_style_attribute_hashes is True

    csp = SecurityHeadersMiddleware(lambda request: None).build_content_security_policy(
        inline_hashes=hashes,
    )

    assert "script-src 'self' 'unsafe-hashes'" in csp
    assert build_csp_sha256("window.bootstrapTheme();") in csp
    assert build_csp_sha256("closeModal()") in csp
    assert "style-src 'self' 'unsafe-inline' 'unsafe-hashes'" in csp
    assert build_csp_sha256(".banner { color: red; }") in csp
    assert "style-src-elem 'self' 'unsafe-inline'" in csp
    assert "style-src-attr 'unsafe-inline'" in csp
    assert build_csp_sha256("display:none") in csp
