from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath


CONTENT_TYPE_ALIASES = {
    "application/x-gzip": "application/gzip",
    "application/x-zip-compressed": "application/zip",
    "audio/x-wav": "audio/wav",
    "binary/octet-stream": "application/octet-stream",
    "text/x-markdown": "text/markdown",
}

STRICT_EXTENSION_CONTENT_TYPES = {
    ".7z": "application/x-7z-compressed",
    ".bz2": "application/x-bzip2",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".gif": "image/gif",
    ".gz": "application/gzip",
    ".imdi": "application/xml",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".tar": "application/x-tar",
    ".wav": "audio/wav",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
    ".xml": "application/xml",
    ".zip": "application/zip",
}

SIGNATURE_REQUIRED_EXTENSIONS = {
    ".7z",
    ".bz2",
    ".docx",
    ".gif",
    ".gz",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pptx",
    ".tar",
    ".wav",
    ".xlsx",
    ".xlsm",
    ".zip",
}

COMPATIBLE_CONTENT_TYPES = (
    {"application/xml", "text/xml"},
    {"audio/wav", "audio/x-wav"},
    {
        "application/zip",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel.sheet.macroenabled.12",
    },
)

RELAXED_DECLARED_TYPES = {"application/octet-stream", "text/plain"}


@dataclass(frozen=True)
class UploadContentInspection:
    normalized_content_type: str
    detected_content_type: str | None
    errors: tuple[str, ...]


def normalize_content_type(content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_ALIASES.get(normalized, normalized)


def inspect_uploaded_content(
    *,
    file_name: str,
    declared_content_type: str | None,
    sample_bytes: bytes,
    blocked_content_types: set[str],
) -> UploadContentInspection:
    normalized_declared_type = normalize_content_type(declared_content_type)
    detected_content_type = detect_content_type(sample_bytes, file_name=file_name)
    errors: list[str] = []

    if detected_content_type and detected_content_type in blocked_content_types:
        errors.append(f"Detected blocked content '{detected_content_type}' in uploaded file.")

    expected_content_type = expected_content_type_for_file_name(file_name)
    extension = PurePosixPath(file_name).suffix.lower()
    if expected_content_type:
        if detected_content_type:
            if not content_types_are_compatible(expected_content_type, detected_content_type):
                errors.append(
                    f"File extension '{extension}' does not match detected content '{detected_content_type}'.",
                )
        elif extension in SIGNATURE_REQUIRED_EXTENSIONS:
            errors.append(
                f"File extension '{extension}' does not match the uploaded content.",
            )

    if (
        detected_content_type
        and normalized_declared_type
        and normalized_declared_type not in RELAXED_DECLARED_TYPES
        and not content_types_are_compatible(normalized_declared_type, detected_content_type)
    ):
        errors.append(
            f"Declared content type '{normalized_declared_type}' does not match detected content '{detected_content_type}'.",
        )

    return UploadContentInspection(
        normalized_content_type=normalized_declared_type,
        detected_content_type=detected_content_type,
        errors=tuple(errors),
    )


def detect_content_type(sample_bytes: bytes, *, file_name: str | None = None) -> str | None:
    if not sample_bytes:
        return None

    stripped = sample_bytes.lstrip()
    lowered = stripped[:512].lower()
    extension = PurePosixPath(file_name or "").suffix.lower()

    if sample_bytes.startswith(b"%PDF-"):
        return "application/pdf"
    if sample_bytes.startswith(b"PK\x03\x04"):
        guessed = expected_content_type_for_file_name(file_name or "")
        if guessed and guessed in COMPATIBLE_CONTENT_TYPES[2]:
            return guessed
        return "application/zip"
    if sample_bytes.startswith(b"\x1f\x8b"):
        return "application/gzip"
    if sample_bytes.startswith(b"BZh"):
        return "application/x-bzip2"
    if sample_bytes.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "application/x-7z-compressed"
    if len(sample_bytes) >= 262 and sample_bytes[257:262] == b"ustar":
        return "application/x-tar"
    if sample_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if sample_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if sample_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if sample_bytes.startswith(b"RIFF") and sample_bytes[8:12] == b"WAVE":
        return "audio/wav"

    if lowered.startswith(b"<svg") or b"<svg" in lowered[:256]:
        return "image/svg+xml"
    if lowered.startswith((b"<!doctype html", b"<html", b"<head", b"<body", b"<script")):
        return "text/html"
    if lowered.startswith(b"<?xml"):
        return "application/xml"
    if extension in {".xml", ".imdi"} and lowered.startswith(b"<") and b"<html" not in lowered[:256]:
        return "application/xml"
    if extension == ".json" and lowered.startswith((b"{", b"[")):
        return "application/json"

    guessed_type, _ = mimetypes.guess_type(file_name or "")
    normalized_guess = normalize_content_type(guessed_type)
    if normalized_guess in {"application/json", "application/xml"}:
        return normalized_guess
    return None


def expected_content_type_for_file_name(file_name: str) -> str | None:
    extension = PurePosixPath(file_name or "").suffix.lower()
    if extension in STRICT_EXTENSION_CONTENT_TYPES:
        return STRICT_EXTENSION_CONTENT_TYPES[extension]

    guessed_type, _ = mimetypes.guess_type(file_name or "")
    normalized_guess = normalize_content_type(guessed_type)
    return normalized_guess or None


def content_types_are_compatible(left: str, right: str) -> bool:
    normalized_left = normalize_content_type(left)
    normalized_right = normalize_content_type(right)
    if normalized_left == normalized_right:
        return True

    return any(
        normalized_left in compatible_group and normalized_right in compatible_group
        for compatible_group in COMPATIBLE_CONTENT_TYPES
    )
