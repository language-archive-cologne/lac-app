"""
Storage cache helpers sharing a common key namespace.

Currently used for ACL payload caching to avoid repeated S3 downloads, but
designed so other storage subsystems can reuse the same primitives.
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
]

_CACHE_NAMESPACE = "storage"
_ACL_NAMESPACE = "acl"
_DEFAULT_ACL_TIMEOUT = getattr(settings, "STORAGE_ACL_CACHE_TIMEOUT", 900)


def build_key(namespace: str, *parts: str) -> str:
    """
    Construct a namespaced cache key with colon separators.
    """
    sanitized = [part.replace(" ", "_") for part in parts if part]
    parts_string = ":".join(sanitized)
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
