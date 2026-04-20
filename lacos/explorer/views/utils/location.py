"""Location and geocoding utility functions."""

import logging
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render


logger = logging.getLogger(__name__)


def get_formatted_location(location):
    """Get formatted location string from location object.

    Falls back to different fields in order of preference:
    location_name > region_name > country_name > coordinates.
    """
    if location:
        if location.location_name:
            return location.location_name
        elif location.region_name:
            return location.region_name
        elif location.country_name:
            return location.country_name
        elif location.geo_location:
            return get_location_from_coordinates(location.geo_location)
    return ""


@lru_cache(maxsize=128)
def get_location_from_coordinates(coordinates):
    """Return "lat, lng" formatted coordinates; no network call.

    Input format: "LATITUDE,LONGITUDE" (e.g. "50.926735,6.930392").
    """
    try:
        safe_coordinates = re.sub(r'[^\w\-]', '_', coordinates)
        cache_key = f"geo_location_{safe_coordinates}"
        cached_result = cache.get(cache_key)
        if cached_result:
            return cached_result

        if not coordinates or ',' not in coordinates:
            return coordinates

        lat, lng = coordinates.split(',')
        lat = lat.strip()
        lng = lng.strip()

        formatted_coords = f"{lat}, {lng}"

        cache.set(cache_key, formatted_coords, timeout=60*60*24*30)

        return formatted_coords

    except Exception as e:
        logger.error("Error fetching location from coordinates", extra={"error": str(e)})
        return coordinates


def map_popup_view(request):
    """HTMX view to render a map popup with the given coordinates."""
    geo = request.GET.get('geo', '')
    title = request.GET.get('title', 'Location')

    if not geo or ',' not in geo:
        return HttpResponse('<p class="text-error">Invalid coordinates</p>', status=400)

    try:
        lat, lng = geo.split(',')
        lat = float(lat.strip())
        lng = float(lng.strip())
    except ValueError:
        return HttpResponse('<p class="text-error">Invalid coordinates format</p>', status=400)

    is_dark = request.COOKIES.get('theme') == 'dark' or request.GET.get('theme') == 'dark'
    style_url = (
        settings.EXPLORER_MAIN_MAP_DARK_STYLE_URL
        if is_dark else settings.EXPLORER_MAIN_MAP_STYLE_URL
    )
    return render(request, 'explorer/partials/map_popup.html', {
        'lat': lat,
        'lng': lng,
        'title': title,
        'map_style_url': style_url,
    })


_STYLE_PATH = Path(settings.APPS_DIR) / "static" / "vendor" / "maps" / "lac" / "natural-earth-c.json"


def map_style_view(request):
    """Serve the LAC Natural Earth style JSON with per-env URLs substituted.

    Placeholders (`__PMTILES_URL__`, `__GLYPHS_URL__`) in the checked-in JSON
    are replaced from Django settings. This keeps the static file clean while
    still letting dev (MinIO) and prod (S3) differ only in env vars.
    """
    if not _STYLE_PATH.is_file():
        return HttpResponseNotFound("style missing")
    body = _STYLE_PATH.read_text(encoding="utf-8")
    body = body.replace("__PMTILES_URL__", settings.EXPLORER_MAP_PMTILES_URL)
    body = body.replace("__GLYPHS_URL__", settings.EXPLORER_MAP_GLYPHS_URL)
    resp = HttpResponse(body, content_type="application/json")
    resp["Cache-Control"] = "public, max-age=300"
    return resp
