"""Tests for the map style view that substitutes pmtiles/glyphs URLs at request time."""

import json
from unittest.mock import patch

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_map_style_view_returns_200(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_map_style_view_returns_json_content_type(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_map_style_view_body_is_valid_json(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    json.loads(response.content)  # raises if invalid


@pytest.mark.django_db
def test_map_style_view_substitutes_pmtiles_placeholder(client, settings):
    response = client.get(reverse("explorer:map_style_ne_c"))
    body = response.content.decode()
    assert "__PMTILES_URL__" not in body
    assert settings.EXPLORER_MAP_PMTILES_URL in body


@pytest.mark.django_db
def test_map_style_view_substitutes_glyphs_placeholder(client, settings):
    response = client.get(reverse("explorer:map_style_ne_c"))
    body = response.content.decode()
    assert "__GLYPHS_URL__" not in body
    assert settings.EXPLORER_MAP_GLYPHS_URL in body


@pytest.mark.django_db
def test_map_style_view_source_url_uses_pmtiles_protocol(client, settings):
    """MapLibre needs `pmtiles://<url>` in the source config to trigger the
    registered protocol handler. A bare HTTPS URL would bypass pmtiles.js."""
    response = client.get(reverse("explorer:map_style_ne_c"))
    style = json.loads(response.content)
    assert style["sources"]["ne"]["url"] == f"pmtiles://{settings.EXPLORER_MAP_PMTILES_URL}"


@pytest.mark.django_db
def test_map_style_view_glyphs_url_has_fontstack_range_template(client):
    """MapLibre GL's `glyphs` URL must contain `{fontstack}` and `{range}`
    placeholders; MapLibre substitutes them per glyph fetch."""
    response = client.get(reverse("explorer:map_style_ne_c"))
    style = json.loads(response.content)
    assert "{fontstack}" in style["glyphs"]
    assert "{range}" in style["glyphs"]


@pytest.mark.django_db
def test_map_style_view_cache_header_present(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    assert response["Cache-Control"] == "public, max-age=86400, stale-while-revalidate=604800"


@pytest.mark.django_db
def test_map_style_view_sets_content_length(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    assert int(response["Content-Length"]) == len(response.content)


def test_render_map_style_body_cache_invalidates_with_mtime(tmp_path):
    from lacos.explorer.views.utils import location as loc

    loc._render_map_style_body.cache_clear()
    style_path = tmp_path / "style.json"
    style_path.write_text(
        '{"version":8,"sources":{"ne":{"url":"pmtiles://__PMTILES_URL__"}},"glyphs":"__GLYPHS_URL__"}',
        encoding="utf-8",
    )

    body = loc._render_map_style_body(str(style_path), 1, "/first.pmtiles", "/glyphs", None)
    style_path.write_text('{"version":8,"name":"changed"}', encoding="utf-8")

    cached_body = loc._render_map_style_body(str(style_path), 1, "/first.pmtiles", "/glyphs", None)
    refreshed_body = loc._render_map_style_body(str(style_path), 2, "/first.pmtiles", "/glyphs", None)

    assert cached_body == body
    assert json.loads(refreshed_body)["name"] == "changed"


@pytest.mark.django_db
def test_map_style_view_projection_can_be_injected_via_query_param(client):
    response = client.get(reverse("explorer:map_style_ne_c"), {"projection": "globe"})
    style = json.loads(response.content)
    assert style["projection"] == {"type": "globe"}


@pytest.mark.django_db
def test_map_style_view_has_no_projection_by_default(client):
    response = client.get(reverse("explorer:map_style_ne_c"))
    style = json.loads(response.content)
    assert "projection" not in style


@pytest.mark.django_db
def test_map_style_view_returns_404_when_style_file_missing(client, tmp_path):
    """If the style file is removed from the static tree, the view must not crash."""
    from lacos.explorer.views.utils import location as loc
    with patch.object(loc, "_STYLE_PATH", tmp_path / "does-not-exist.json"):
        response = client.get(reverse("explorer:map_style_ne_c"))
    assert response.status_code == 404
