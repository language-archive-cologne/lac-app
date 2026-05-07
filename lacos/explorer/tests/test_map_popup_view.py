"""Tests for the map popup view (HTMX endpoint for detail map modals)."""

from pathlib import Path

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_map_popup_view_returns_200_with_valid_coords(client):
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "50.9254927,6.9328194", "title": "Cologne"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_map_popup_view_rejects_invalid_coords(client):
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "nonsense"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_map_popup_view_style_url_is_not_third_party(client):
    """GDPR invariant: the map popup must never reference a third-party tile CDN."""
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "50.9254927,6.9328194", "title": "x"})
    body = response.content.decode()
    blocklist = [
        "tiles.openfreemap.org",
        "demotiles.maplibre.org",
        "tile.openstreetmap.org",
    ]
    for forbidden in blocklist:
        assert forbidden not in body, f"third-party domain leaked into popup: {forbidden}"


@pytest.mark.django_db
def test_map_popup_view_passes_lac_style_url(client, settings):
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "50.9254927,6.9328194", "title": "x"})
    body = response.content.decode()
    assert settings.EXPLORER_MAIN_MAP_STYLE_URL in body


@pytest.mark.django_db
def test_map_popup_view_bootstraps_local_map_dependencies(client):
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "50.9254927,6.9328194", "title": "x"})
    body = response.content.decode()

    assert "data-map-popup" in body
    assert 'class="lac-map-popup"' in body
    assert "data-lat=\"50.9254927\"" in body
    assert "data-lng=\"6.9328194\"" in body
    assert "vendor/js/maplibre-gl/maplibre-gl.js" in body
    assert "vendor/js/pmtiles/pmtiles.js" in body


@pytest.mark.django_db
def test_map_popup_view_does_not_include_inline_script_or_style(client):
    url = reverse("explorer:map_popup")
    response = client.get(url, {"geo": "50.9254927,6.9328194", "title": "x"})
    body = response.content.decode()

    assert "<script" not in body.lower()
    assert " style=" not in body.lower()


def test_map_popup_has_css_backed_dimensions():
    css = Path("lacos/static/css/project.css").read_text()

    assert ".lac-map-popup" in css
    assert "height: 400px;" in css
    assert "min-height: 400px;" in css
