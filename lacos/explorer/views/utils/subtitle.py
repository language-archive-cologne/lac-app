"""Subtitle file matching utilities."""

import logging
from pathlib import Path
from typing import Optional

from lacos.explorer.media_utils import SUBTITLE_EXTENSIONS

from .resource import iter_bundle_resources
from .storage import resolve_resource_to_presigned


logger = logging.getLogger(__name__)


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
    video_stem = Path(video_resource.file_name).stem.lower()

    for resource in iter_bundle_resources(bundle):
        if resource.id == video_resource.id:
            continue

        file_name = getattr(resource, "file_name", None)
        if not file_name:
            continue

        ext = Path(file_name).suffix.lower()
        if ext not in SUBTITLE_EXTENSIONS:
            continue

        if Path(file_name).stem.lower() != video_stem:
            continue

        resolution = resolve_resource_to_presigned(
            resource_service,
            resource,
            bundle,
            collection_for_path,
        )
        if resolution:
            return resolution["url"]

    return None
