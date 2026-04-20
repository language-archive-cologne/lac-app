"""Tests for explorer map configuration settings."""

import pytest
from django.conf import settings


def test_pmtiles_url_default_targets_local_minio():
    assert settings.EXPLORER_MAP_PMTILES_URL == "http://localhost:9100/lacos-maps/ne.pmtiles"


def test_glyphs_url_default_targets_local_minio():
    assert settings.EXPLORER_MAP_GLYPHS_URL == "http://localhost:9100/lacos-maps/glyphs"


def test_main_style_url_default_points_to_lac_natural_earth():
    assert settings.EXPLORER_MAIN_MAP_STYLE_URL == "/static/vendor/maps/lac/natural-earth-c.json"


def test_glyphs_url_does_not_contain_trailing_slash():
    """Style JSON templates the URL as `{glyphs}/{fontstack}/{range}.pbf` — a trailing
    slash would double up and break glyph fetches."""
    assert not settings.EXPLORER_MAP_GLYPHS_URL.endswith("/")
