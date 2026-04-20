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
    assert "max-age" in response["Cache-Control"]


@pytest.mark.django_db
def test_map_style_view_returns_404_when_style_file_missing(client, tmp_path):
    """If the style file is removed from the static tree, the view must not crash."""
    from lacos.explorer.views.utils import location as loc
    with patch.object(loc, "_STYLE_PATH", tmp_path / "does-not-exist.json"):
        response = client.get(reverse("explorer:map_style_ne_c"))
    assert response.status_code == 404
