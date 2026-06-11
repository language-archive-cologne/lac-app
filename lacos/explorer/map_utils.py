"""Map utilities for the explorer app."""
import json

from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.urls import reverse


MAP_MARKERS_CACHE_KEY = "explorer:map_markers:v6"
MAP_MARKERS_CACHE_TIMEOUT = 86400  # 24 hours (invalidated on collection changes)


def _all_map_collections():
    """Queryset of every collection with its map-relevant data prefetched.

    The map always shows all collections regardless of the caller's language
    or pagination filter, so the client can highlight/dim and zoom without
    losing pins. Exposure policy is intentionally not applied here — the
    map is a public overview and cache is shared across users.
    """
    from lacos.blam.models import Collection
    from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo

    return Collection.objects.prefetch_related(
        Prefetch(
            'general_info',
            queryset=CollectionGeneralInfo.objects.select_related('location').prefetch_related(
                'object_languages',
            ),
            to_attr='prefetched_general_info',
        ),
    ).annotate(
        bundles_count=Count('bundle_collection', distinct=True)
    )


def _group_markers_by_coordinates(markers):
    """Collapse exact coordinate duplicates into a single map point."""
    grouped = {}
    order = []
    for marker in markers:
        key = (marker["lat"], marker["lng"])
        if key not in grouped:
            grouped[key] = {
                "lat": marker["lat"],
                "lng": marker["lng"],
                "collections": [],
            }
            order.append(key)
        grouped[key]["collections"].append({
            "title": marker["title"],
            "url": marker["url"],
            "languages": marker["languages"],
            "language_keys": marker["language_keys"],
            "country": marker["country"],
            "bundles": marker["bundles"],
        })

    markers_by_coordinate = []
    for key in order:
        group = grouped[key]
        collections = group["collections"]
        countries = sorted({item["country"] for item in collections if item["country"]})
        language_keys = sorted({
            key
            for item in collections
            for key in item["language_keys"]
        })
        language_entries = []
        seen_languages = set()
        for item in collections:
            for language in item["languages"]:
                language_key = (
                    language.get("display_name"),
                    language.get("name"),
                    language.get("iso"),
                    language.get("glottocode"),
                )
                if language_key in seen_languages:
                    continue
                seen_languages.add(language_key)
                language_entries.append(language)

        first = collections[0]
        is_group = len(collections) > 1
        markers_by_coordinate.append({
            "lat": group["lat"],
            "lng": group["lng"],
            "title": f"{len(collections)} collections" if is_group else first["title"],
            "url": "" if is_group else first["url"],
            "languages": language_entries,
            "language_keys": language_keys,
            "country": ", ".join(countries),
            "bundles": sum(item["bundles"] for item in collections),
            "collections": collections,
        })

    return markers_by_coordinate


def get_collection_map_markers(collections=None):
    """Return JSON markers for every collection with a geo_location.

    `collections` is accepted for backwards compatibility but ignored; markers
    are always built from the full queryset so the map can show all pins and
    filter client-side. Result is cached under a single key.
    """
    cached_markers = cache.get(MAP_MARKERS_CACHE_KEY)
    if cached_markers is not None:
        return cached_markers

    markers = []
    for collection in _all_map_collections():
        try:
            gi_list = getattr(collection, 'prefetched_general_info', None)
            gi = gi_list[0] if gi_list else collection.get_general_info
            geo = None
            if gi and gi.location:
                geo = gi.location.geo_location
            if not geo or ',' not in geo:
                continue

            lat, lng = geo.split(',')
            title = (
                (gi.display_title if gi else None)
                or (gi.title if gi else None)
                or collection.identifier
            )
            languages = []
            language_keys = set()
            if gi:
                for language in gi.object_languages.all():
                    entry = {
                        "name": language.name,
                        "display_name": language.display_name,
                        "iso": language.iso_639_3_code,
                        "glottocode": language.glottolog_code,
                    }
                    languages.append(entry)
                    for value in entry.values():
                        if value:
                            language_keys.add(str(value).lower())
            country = gi.location.country_facet if gi and gi.location else None
            bundles = getattr(collection, 'bundles_count', 0)
            markers.append({
                'lat': float(lat.strip()),
                'lng': float(lng.strip()),
                'title': title,
                'url': reverse('explorer:collection_detail', kwargs={'pk': collection.pk}),
                'languages': languages,
                'language_keys': sorted(language_keys),
                'country': country or '',
                'bundles': int(bundles or 0),
            })
        except (ValueError, AttributeError):
            pass

    markers_json = json.dumps(_group_markers_by_coordinates(markers))
    cache.set(MAP_MARKERS_CACHE_KEY, markers_json, MAP_MARKERS_CACHE_TIMEOUT)
    return markers_json


def invalidate_map_markers_cache():
    """Invalidate the map markers cache. Call this when collections are modified."""
    cache.delete(MAP_MARKERS_CACHE_KEY)
