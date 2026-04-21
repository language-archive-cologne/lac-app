"""Signed access tokens for IMDI XML browsing."""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from django.core import signing
from django.core.exceptions import PermissionDenied


IMDI_ACCESS_SALT = "lacos.explorer.imdi"
IMDI_ALLOWED_SUFFIXES = {".imdi", ".xml"}
IMDI_MARKER_DIRECTORIES = {"content", "derivatives", "metadata"}


def build_imdi_access_token(*, bucket: str, root_key: str) -> str:
    normalized_root_key = _normalize_imdi_key(root_key)
    payload = {
        "bucket": bucket,
        "root_key": normalized_root_key,
        "allowed_prefix": _derive_allowed_prefix(normalized_root_key),
    }
    return signing.dumps(payload, salt=IMDI_ACCESS_SALT)


def resolve_imdi_access(token: str, *, requested_key: str | None = None, max_age: int = 3600) -> tuple[str, str]:
    try:
        payload = signing.loads(token, salt=IMDI_ACCESS_SALT, max_age=max_age)
    except signing.BadSignature as exc:
        raise PermissionDenied("Invalid IMDI access token.") from exc

    bucket = payload.get("bucket")
    root_key = _normalize_imdi_key(payload.get("root_key"))
    allowed_prefix = payload.get("allowed_prefix") or None
    target_key = _normalize_imdi_key(requested_key or root_key)

    if not bucket:
        raise PermissionDenied("Invalid IMDI access token.")
    if not _is_allowed_imdi_key(target_key, allowed_prefix=allowed_prefix, root_key=root_key):
        raise PermissionDenied("Requested IMDI resource is out of scope.")

    return bucket, target_key


def _normalize_imdi_key(key: str | None) -> str:
    raw_key = (key or "").replace("\\", "/").strip()
    if not raw_key:
        raise PermissionDenied("IMDI key is required.")

    normalized = posixpath.normpath(raw_key)
    if normalized in {"", ".", "/"} or normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise PermissionDenied("Invalid IMDI key.")

    return normalized.lstrip("/")


def _derive_allowed_prefix(root_key: str) -> str | None:
    parts = PurePosixPath(root_key).parts
    for index, part in enumerate(parts):
        if part in IMDI_MARKER_DIRECTORIES and index > 0:
            return "/".join(parts[:index]) + "/"

    parent = str(PurePosixPath(root_key).parent)
    if parent and parent != ".":
        return parent.rstrip("/") + "/"
    return None


def _is_allowed_imdi_key(target_key: str, *, allowed_prefix: str | None, root_key: str) -> bool:
    suffix = PurePosixPath(target_key).suffix.lower()
    if suffix not in IMDI_ALLOWED_SUFFIXES:
        return False
    if allowed_prefix is None:
        return target_key == root_key
    return target_key.startswith(allowed_prefix)
