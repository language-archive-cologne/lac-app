"""Utility functions for explorer views."""

from .bundle import (
    BUNDLES_PER_PAGE,
    build_bundle_context,
    bundle_queryset_for_collection,
    paginate_bundle_contexts,
    summarize_bundle_access_levels_by_collection_ids,
    summarize_collection_bundle_access_levels,
)
from .elan import (
    parse_elan_document,
    parse_elan_text,
    pick_elan_audio_resource,
)
from .location import (
    get_formatted_location,
    get_location_from_coordinates,
    map_popup_view,
)
from .resource import (
    annotate_resource,
    find_resource_in_bundle,
    iter_bundle_resources,
    prepare_resource_lists,
)
from .storage import (
    build_content_disposition,
    load_xml_preview,
    resolve_existing_object,
    resolve_resource_to_presigned,
)
from .lookup import (
    get_object_by_pk_or_handle,
    HandleLookupMixin,
)


__all__ = [
    # Bundle utilities
    "BUNDLES_PER_PAGE",
    "build_bundle_context",
    "bundle_queryset_for_collection",
    "paginate_bundle_contexts",
    "summarize_bundle_access_levels_by_collection_ids",
    "summarize_collection_bundle_access_levels",
    # ELAN utilities
    "parse_elan_document",
    "parse_elan_text",
    "pick_elan_audio_resource",
    # Location utilities
    "get_formatted_location",
    "get_location_from_coordinates",
    "map_popup_view",
    # Resource utilities
    "annotate_resource",
    "find_resource_in_bundle",
    "iter_bundle_resources",
    "prepare_resource_lists",
    # Storage utilities
    "build_content_disposition",
    "load_xml_preview",
    "resolve_existing_object",
    "resolve_resource_to_presigned",
    # Lookup utilities
    "get_object_by_pk_or_handle",
    "HandleLookupMixin",
]
