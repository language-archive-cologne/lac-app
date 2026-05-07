"""Subtitle file matching utilities."""

import logging
from pathlib import Path
from typing import Optional

from lacos.explorer.media_utils import SUBTITLE_EXTENSIONS

from .resource import iter_bundle_resources
from .storage import resolve_collection_metadata_to_presigned, resolve_resource_to_presigned


logger = logging.getLogger(__name__)


def _iter_matching_subtitles(resources, video_resource):
    video_stem = Path(video_resource.file_name).stem.lower()
    video_id = getattr(video_resource, "id", None)

    for resource in resources:
        if video_id is not None and getattr(resource, "id", None) == video_id:
            continue

        file_name = getattr(resource, "file_name", None)
        if not file_name:
            continue

        ext = Path(file_name).suffix.lower()
        if ext not in SUBTITLE_EXTENSIONS:
            continue

        if Path(file_name).stem.lower() != video_stem:
            continue

        yield resource


def find_subtitle_for_video(
    bundle,
    video_resource,
    resource_service,
    collection_for_path,
) -> Optional[str]:
    """Find a subtitle file matching the video and return its presigned URL.

    Iterates bundle resources looking for a subtitle file whose stem matches
    the video file's stem (case-insensitive). Returns the presigned URL of
    the first match, or ``None`` if no subtitle is found.
    """
    for resource in _iter_matching_subtitles(iter_bundle_resources(bundle), video_resource):
        resolution = resolve_resource_to_presigned(
            resource_service,
            resource,
            bundle,
            collection_for_path,
        )
        if resolution:
            return resolution["url"]

    return None


def find_subtitle_for_collection_video(
    collection,
    structural_info,
    video_resource,
    resource_service,
) -> Optional[str]:
    """Find a collection metadata subtitle matching the video file."""
    metadata_files = getattr(structural_info, "additional_metadata_files", None)
    if metadata_files is None:
        return None

    resources = metadata_files.all() if hasattr(metadata_files, "all") else metadata_files
    for resource in _iter_matching_subtitles(resources, video_resource):
        resolution = resolve_collection_metadata_to_presigned(
            resource_service,
            resource,
            collection,
        )
        if resolution:
            return resolution["url"]

    return None
