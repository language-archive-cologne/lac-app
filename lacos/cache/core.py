"""
Shared cache helpers for storage and ACL subsystems.

This module centralises cache key construction, payload serialisation, and
convenience accessors so different parts of the project can share the same
Redis-backed (or Django cache) implementation without duplicating logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

__all__ = [
    "StorageCacheEntry",
    "build_key",
    "get_acl_entry",
    "set_acl_entry",
    "invalidate_acl_entry",
    "get_folder_listing_entry",
    "set_folder_listing_entry",
    "invalidate_folder_listing",
    "invalidate_folder_listing_many",
]

_CACHE_NAMESPACE = "storage"
_ACL_NAMESPACE = "acl"
_DEFAULT_ACL_TIMEOUT = getattr(settings, "STORAGE_ACL_CACHE_TIMEOUT", 900)
_FOLDER_NAMESPACE = "folders"
_FOLDER_VERSION_SUFFIX = "__v"


def build_key(namespace: str, *parts: str) -> str:
    """
    Construct a namespaced cache key with colon separators.
    """
    sanitised = [part.replace(" ", "_") for part in parts if part]
    parts_string = ":".join(sanitised)
    return f"{_CACHE_NAMESPACE}:{namespace}:{parts_string}"


@dataclass
class StorageCacheEntry:
    data: Any = None
    found: bool = True
    error: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> Dict[str, Any]:
        payload = {
            "data": self.data,
            "found": self.found,
            "error": self.error,
            "etag": self.etag,
            "last_modified": self.last_modified,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "StorageCacheEntry":
        return cls(
            data=payload.get("data"),
            found=payload.get("found", True),
            error=payload.get("error"),
            etag=payload.get("etag"),
            last_modified=payload.get("last_modified"),
            metadata=payload.get("metadata", {}) or {},
        )


def get_acl_entry(bucket: str, key: str) -> Optional[StorageCacheEntry]:
    cache_key = build_key(_ACL_NAMESPACE, bucket, key)
    payload = cache.get(cache_key)
    if payload is None:
        return None
    return StorageCacheEntry.from_payload(payload)


def set_acl_entry(
    bucket: str,
    key: str,
    *,
    data: Any,
    found: bool,
    error: Optional[str],
    etag: Optional[str],
    last_modified: Optional[Any],
    metadata: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
) -> None:
    cache_key = build_key(_ACL_NAMESPACE, bucket, key)
    entry = StorageCacheEntry(
        data=data,
        found=found,
        error=error,
        etag=etag,
        last_modified=str(last_modified) if last_modified is not None else None,
        metadata=metadata or {},
    )
    cache.set(cache_key, entry.as_payload(), timeout=timeout or _DEFAULT_ACL_TIMEOUT)


def invalidate_acl_entry(bucket: str, key: str) -> None:
    cache_key = build_key(_ACL_NAMESPACE, bucket, key)
    cache.delete(cache_key)


# ---------------------------------------------------------------------------
# Folder listing helpers
# ---------------------------------------------------------------------------

def _folder_cache_enabled() -> bool:
    return getattr(settings, "STORAGE_FOLDER_CACHE_ENABLED", True)


def _normalise_prefix(prefix: Optional[str]) -> str:
    if not prefix:
        return "__root__"
    value = prefix.strip("/")
    return value or "__root__"


def _folder_version_key(bucket: str) -> str:
    return build_key(_FOLDER_NAMESPACE, bucket, _FOLDER_VERSION_SUFFIX)


def _get_folder_version(bucket: str) -> int:
    version_key = _folder_version_key(bucket)
    version = cache.get(version_key)
    if version is None:
        version = 1
        cache.set(version_key, version, timeout=None)
    return int(version)


def _compose_folder_key(bucket: str, prefix: Optional[str], version: int) -> str:
    return build_key(_FOLDER_NAMESPACE, bucket, str(version), _normalise_prefix(prefix))


def get_folder_listing_entry(bucket: str, prefix: Optional[str]) -> Optional[StorageCacheEntry]:
    """
    Retrieve cached folder listing for the given bucket/prefix combo.
    """
    if not _folder_cache_enabled():
        return None
    version = _get_folder_version(bucket)
    cache_key = _compose_folder_key(bucket, prefix, version)
    payload = cache.get(cache_key)
    if payload is None:
        return None
    entry = StorageCacheEntry.from_payload(payload)
    entry.metadata.setdefault("version", version)
    return entry


def set_folder_listing_entry(
    bucket: str,
    prefix: Optional[str],
    *,
    data: Any,
    etag: Optional[str] = None,
    last_modified: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Store folder listing payload without expiration.
    """
    if not _folder_cache_enabled():
        return
    version = _get_folder_version(bucket)
    cache_key = _compose_folder_key(bucket, prefix, version)
    entry = StorageCacheEntry(
        data=data,
        found=True,
        error=None,
        etag=etag,
        last_modified=str(last_modified) if last_modified is not None else None,
        metadata=metadata or {},
    )
    cache.set(cache_key, entry.as_payload(), timeout=None)


def invalidate_folder_listing(bucket: str, prefix: Optional[str] = None) -> None:
    """
    Invalidate cached folder listings.
    - prefix=None => bump bucket version to invalidate all prefixes.
    - prefix=str => remove cached entry for specific prefix.
    """
    if not _folder_cache_enabled():
        return
    if prefix is None:
        version_key = _folder_version_key(bucket)
        try:
            cache.incr(version_key)
        except ValueError:
            cache.set(version_key, 2, timeout=None)
        return

    version = _get_folder_version(bucket)
    cache_key = _compose_folder_key(bucket, prefix, version)
    cache.delete(cache_key)


def invalidate_folder_listing_many(bucket: str, prefixes: Optional[list[Optional[str]]] = None) -> None:
    if not _folder_cache_enabled():
        return
    if not prefixes:
        invalidate_folder_listing(bucket)
        return
    for prefix in prefixes:
        invalidate_folder_listing(bucket, prefix)
