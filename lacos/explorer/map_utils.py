"""Map utilities for the explorer app."""
import json

from django.core.cache import cache
from django.urls import reverse


MAP_MARKERS_CACHE_KEY = "explorer:map_markers"
MAP_MARKERS_CACHE_TIMEOUT = 86400  # 24 hours (invalidated on collection changes)


def get_collection_map_markers(collections):
    """Extract map markers from a list of collections.

    Expects collections to have geo_location already set by the view.
    Returns a JSON string of markers with lat, lng, title, and url.
    Uses caching to avoid regenerating markers on every request.
    """
    # Try to get cached markers
    cached_markers = cache.get(MAP_MARKERS_CACHE_KEY)
    if cached_markers is not None:
        return cached_markers

    markers = []
    for collection in collections:
        geo = getattr(collection, 'geo_location', None)
        if not geo or ',' not in geo:
            continue
        try:
            lat, lng = geo.split(',')
            # Use prefetched data if available, fall back to get_general_info
            gi_list = getattr(collection, 'prefetched_general_info', None)
            gi = gi_list[0] if gi_list else collection.get_general_info
            title = (
                (gi.display_title if gi else None)
                or (gi.title if gi else None)
                or collection.identifier
            )
            markers.append({
                'lat': float(lat.strip()),
                'lng': float(lng.strip()),
                'title': title,
                'url': reverse('explorer:collection_detail', kwargs={'pk': collection.pk}),
            })
        except (ValueError, AttributeError):
            pass

    markers_json = json.dumps(markers)
    cache.set(MAP_MARKERS_CACHE_KEY, markers_json, MAP_MARKERS_CACHE_TIMEOUT)
    return markers_json


def invalidate_map_markers_cache():
    """Invalidate the map markers cache. Call this when collections are modified."""
    cache.delete(MAP_MARKERS_CACHE_KEY)
