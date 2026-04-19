"""Location and geocoding utility functions."""

import logging
import re
from functools import lru_cache

from django.core.cache import cache
from django.http import HttpResponse
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
    """Get location name from coordinates using Nominatim (OpenStreetMap).

    Coordinates should be in format "LATITUDE,LONGITUDE" like "50.926735,6.930392"
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

    from django.conf import settings
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
