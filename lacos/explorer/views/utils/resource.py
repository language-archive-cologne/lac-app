"""Resource utility functions for annotating and preparing resource lists."""

from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import unquote

from lacos.explorer.media_utils import determine_media_type


def annotate_resource(resource):
    """Add detected_media_type attribute to a resource based on mime_type and file_name."""
    if resource is None:
        return None

    resource.detected_media_type = determine_media_type(
        getattr(resource, "mime_type", None),
        getattr(resource, "file_name", None),
    )
    return resource


def prepare_resource_lists(resources_container):
    """Prepare categorized resource lists from a resources container.

    Returns tuple of (media_resources, written_resources, other_resources).
    Moves audio/video resources from 'other' to 'media' category.
    """
    if not resources_container:
        return [], [], []

    media = [annotate_resource(res) for res in resources_container.bundle_media_resources.all()]
    written = [annotate_resource(res) for res in resources_container.bundle_written_resources.all()]
    other = [annotate_resource(res) for res in resources_container.bundle_other_resources.all()]

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
