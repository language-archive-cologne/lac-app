from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

AUDIO_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".m4b",
    ".mp3",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".wma",
}

VIDEO_EXTENSIONS = {
    ".3gp",
    ".3g2",
    ".avi",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogv",
    ".ts",
    ".webm",
    ".wmv",
}

IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".tif",
    ".tiff",
    ".webp",
}

PDF_EXTENSIONS = {".pdf"}
XML_EXTENSIONS = {".xml", ".imdi", ".cmdi"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
ANNOTATION_EXTENSIONS = {".eaf", ".elan"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".sub"}


def _normalize_mime(mime_type: Optional[str]) -> str:
    return (mime_type or "").strip().lower()


def _extract_extension(file_name: Optional[str]) -> str:
    if not file_name:
        return ""
    return Path(file_name).suffix.lower()


def determine_media_type(
    mime_type: Optional[str],
    file_name: Optional[str],
) -> Optional[str]:
    """
    Infer the media type for a resource based on its MIME type and file extension.

    Returns one of ``audio``, ``video``, ``image``, ``pdf``, ``xml``, ``markdown``
    or ``None`` when no sensible inference can be made.
    """
    normalized_mime = _normalize_mime(mime_type)
    extension = _extract_extension(file_name)

    if normalized_mime.startswith("audio/"):
        return "audio"
    if normalized_mime.startswith("video/"):
        return "video"
    if normalized_mime.startswith("image/"):
        return "image"
    if normalized_mime == "application/pdf":
        return "pdf"
    if normalized_mime in {"application/xml", "text/xml"} or normalized_mime.endswith("+xml"):
        return "xml"
    if normalized_mime == "text/markdown":
        return "markdown"

    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in PDF_EXTENSIONS:
        return "pdf"
    if extension in XML_EXTENSIONS:
        return "xml"
    if extension in MARKDOWN_EXTENSIONS:
        return "markdown"

    return None


def is_media_type(
    mime_type: Optional[str],
    file_name: Optional[str],
    target_type: str,
) -> bool:
    """
    Return ``True`` when the supplied resource metadata matches ``target_type``.
    """
    if not target_type:
        return False
    detected = determine_media_type(mime_type, file_name)
    return detected == target_type.strip().lower()


def is_annotation_file(
    mime_type: Optional[str],
    file_name: Optional[str],
) -> bool:
    """Return True when the resource is an ELAN annotation file (.eaf/.elan)."""
    normalized = _normalize_mime(mime_type)
    if normalized == "text/x-eaf+xml":
        return True
    ext = _extract_extension(file_name)
    return ext in ANNOTATION_EXTENSIONS


def is_subtitle_file(
    mime_type: Optional[str],
    file_name: Optional[str],
) -> bool:
    """Return True when the resource is a subtitle file (.srt/.vtt/.sub)."""
    normalized = _normalize_mime(mime_type)
    if normalized in {"text/srt", "text/vtt", "application/x-subrip"}:
        return True
    ext = _extract_extension(file_name)
    return ext in SUBTITLE_EXTENSIONS


def guess_source_mime_type(
    mime_type: Optional[str],
    file_name: Optional[str],
    media_type: Optional[str],
) -> str:
    """
    Provide a reasonable MIME type string for the HTML media player.
    """
    normalized = _normalize_mime(mime_type)
    if normalized:
        return normalized

    guess, _ = mimetypes.guess_type(file_name or "")
    if guess:
        return guess

    if media_type == "audio":
        return "audio/mpeg"
    if media_type == "video":
        return "video/mp4"
    if media_type == "image":
        return "image/jpeg"
    if media_type == "pdf":
        return "application/pdf"
    if media_type == "xml":
        return "application/xml"

    return "application/octet-stream"
