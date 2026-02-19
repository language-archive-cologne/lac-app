"""Resource utility functions for annotating and preparing resource lists."""

from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from lacos.explorer.media_utils import determine_media_type
from lacos.storage.models.s3_resource_location import S3ResourceLocation


def _content_type_for_resource(resource, *, content_type_cache=None):
    model_cls = resource.__class__
    if content_type_cache is not None and model_cls in content_type_cache:
        return content_type_cache[model_cls]
    content_type = ContentType.objects.get_for_model(resource)
    if content_type_cache is not None:
        content_type_cache[model_cls] = content_type
    return content_type


def _resource_location_lookup_key(resource, *, content_type_cache=None):
    resource_id = getattr(resource, "id", None)
    if resource is None or resource_id is None:
        return None
    content_type = _content_type_for_resource(resource, content_type_cache=content_type_cache)
    return (content_type.pk, str(resource_id))


def build_s3_location_lookup(resources: Iterable, *, content_type_cache=None):
    """Build a lookup map {(content_type_id, object_id): S3ResourceLocation}."""
    ids_by_content_type: dict[int, set[str]] = {}

    for resource in resources:
        key = _resource_location_lookup_key(resource, content_type_cache=content_type_cache)
        if not key:
            continue
        content_type_id, object_id = key
        ids_by_content_type.setdefault(content_type_id, set()).add(object_id)

    if not ids_by_content_type:
        return {}

    query = Q()
    for content_type_id, object_ids in ids_by_content_type.items():
        query |= Q(content_type_id=content_type_id, object_id__in=object_ids)

    location_lookup = {}
    for location in S3ResourceLocation.objects.filter(query).order_by("id"):
        key = (location.content_type_id, str(location.object_id))
        location_lookup.setdefault(key, location)

    return location_lookup


def annotate_resource(resource, *, s3_locations_by_resource=None, content_type_cache=None):
    """Add detected_media_type and s3_location attributes to a resource."""
    if resource is None:
        return None

    resource.detected_media_type = determine_media_type(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
    )

    # Look up S3 location for size info
    try:
        if hasattr(resource, "_prefetched_s3_location"):
            s3_location = resource._prefetched_s3_location
        elif s3_locations_by_resource is not None:
            key = _resource_location_lookup_key(resource, content_type_cache=content_type_cache)
            s3_location = s3_locations_by_resource.get(key) if key else None
        else:
            content_type = _content_type_for_resource(
                resource,
                content_type_cache=content_type_cache,
            )
            s3_location = S3ResourceLocation.objects.filter(
                content_type=content_type,
                object_id=str(resource.id),
            ).first()
        resource.s3_location = s3_location
        resource.size_bytes = s3_location.size_bytes if s3_location else 0
    except Exception:
        resource.s3_location = None
        resource.size_bytes = 0

    return resource


def prepare_resource_lists(
    resources_container,
    *,
    s3_locations_by_resource=None,
    content_type_cache=None,
):
    """Prepare categorized resource lists from a resources container.

    Returns tuple of (media_resources, written_resources, other_resources).
    Moves audio/video resources from 'other' to 'media' category.
    """
    if not resources_container:
        return [], [], []

    media = [
        annotate_resource(
            res,
            s3_locations_by_resource=s3_locations_by_resource,
            content_type_cache=content_type_cache,
        )
        for res in resources_container.bundle_media_resources.all()
    ]
    written = [
        annotate_resource(
            res,
            s3_locations_by_resource=s3_locations_by_resource,
            content_type_cache=content_type_cache,
        )
        for res in resources_container.bundle_written_resources.all()
    ]
    other = [
        annotate_resource(
            res,
            s3_locations_by_resource=s3_locations_by_resource,
            content_type_cache=content_type_cache,
        )
        for res in resources_container.bundle_other_resources.all()
    ]

    media = [res for res in media if res]
    written = [res for res in written if res]
    other = [res for res in other if res]

    media_candidates = [
        res for res in other
        if getattr(res, "detected_media_type", None) in {"audio", "video"}
    ]
    if media_candidates:
        media.extend(media_candidates)
        other = [res for res in other if res not in media_candidates]

    return media, written, other


def iter_bundle_resources(bundle) -> Iterable:
    """Yield all resources associated with a bundle."""
    resources_container = bundle.resources.first()
    if resources_container:
        yield from resources_container.bundle_media_resources.all()
        yield from resources_container.bundle_written_resources.all()
        yield from resources_container.bundle_other_resources.all()

    struct_info = bundle.structural_info.first()
    if struct_info:
        yield from struct_info.additional_metadata_files.all()


def find_resource_in_bundle(
    bundle,
    *,
    resource_id: Optional[str] = None,
    file_pid: Optional[str] = None,
):
    """Locate a resource within a bundle by id or PID."""
    if resource_id is None and file_pid is None:
        return None

    for resource in iter_bundle_resources(bundle):
        if resource_id is not None and str(resource.id) == str(resource_id):
            return resource
        if file_pid is not None and getattr(resource, 'file_pid', None) == file_pid:
            return resource

    return None
