"""Tests for the map popup view (HTMX endpoint for detail map modals)."""

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
    # The template JSON-encodes the style URL inside a JS literal, so hyphens are
    # escaped as \u002D.  Decode the body with unicode_escape to restore them.
    body = response.content.decode("unicode_escape", errors="replace")
    assert settings.EXPLORER_MAIN_MAP_STYLE_URL in body
