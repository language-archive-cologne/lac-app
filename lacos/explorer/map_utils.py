"""Map utilities for the explorer app."""
import json

from django.urls import reverse


def get_collection_map_markers(collections):
    """Extract map markers from a list of collections.

    Expects collections to have geo_location already set by the view.
    Returns a JSON string of markers with lat, lng, title, and url.
    """
    markers = []
    for collection in collections:
        geo = getattr(collection, 'geo_location', None)
        if not geo or ',' not in geo:
            continue
        try:
            lat, lng = geo.split(',')
            gi = collection.get_general_info
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
    return json.dumps(markers)
