"""Lightweight cache helper for bucket folder structures."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Optional

from django.conf import settings

from lacos.cache.core import (
    get_folder_listing_entry,
    set_folder_listing_entry,
    invalidate_folder_listing,
    invalidate_folder_listing_many,
)
from lacos.storage.observability import record_cache_event

logger = logging.getLogger(__name__)


class FolderStructureCacheService:
    """Ad-hoc cache wrapper to store folder listings per bucket."""

    def __init__(self, timeout: int = 300) -> None:
        self.timeout = timeout  # Retained for backwards compatibility
        self.enabled = getattr(settings, "STORAGE_FOLDER_CACHE_ENABLED", True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, bucket_name: str, folder_path: Optional[str]) -> Optional[Any]:
        if not self.enabled:
            record_cache_event(
                event="folder_cache_get",
                bucket=bucket_name,
                prefix=folder_path or "",
                hit=False,
                metadata={"disabled": True},
            )
            return None

        entry = get_folder_listing_entry(bucket_name, folder_path)
        if entry and entry.found and entry.data is not None:
            logger.debug(
                "Folder cache hit for %s:%s (v%s)",
                bucket_name,
                folder_path,
                entry.metadata.get("version"),
            )
            record_cache_event(
                event="folder_cache_get",
                bucket=bucket_name,
                prefix=folder_path or "",
                hit=True,
                metadata={
                    "version": entry.metadata.get("version"),
                    "item_count": isinstance(entry.data, (list, tuple))
                    and len(entry.data)
                    or getattr(entry.data, "__len__", lambda: None)(),
                },
            )
            return deepcopy(entry.data)
        record_cache_event(
            event="folder_cache_get",
            bucket=bucket_name,
            prefix=folder_path or "",
            hit=False,
            metadata={
                "version": entry.metadata.get("version") if entry else None,
                "disabled": False,
            },
        )
        return None

    def set(self, bucket_name: str, folder_path: Optional[str], value: Any) -> None:
        if not self.enabled:
            return

        payload = deepcopy(value)
        item_count = None
        has_more = None
        if isinstance(payload, dict) and "children" in payload:
            item_count = len(payload.get("children", []))
        elif hasattr(payload, "__len__"):
            try:
                item_count = len(payload)
            except Exception:  # pragma: no cover - defensive
                item_count = None
        if hasattr(payload, "has_more"):
            has_more = getattr(payload, "has_more")

        metadata = {}
        if item_count is not None:
            metadata["item_count"] = item_count
        if has_more is not None:
            metadata["has_more"] = has_more

        set_folder_listing_entry(
            bucket_name,
            folder_path,
            data=payload,
            metadata=metadata,
        )
        logger.debug("Folder cache stored for %s:%s", bucket_name, folder_path)
        record_cache_event(
            event="folder_cache_set",
            bucket=bucket_name,
            prefix=folder_path or "",
            hit=True,
            metadata=metadata,
        )

    def invalidate(self, bucket_name: str, folder_path: Optional[str] = None) -> None:
        if not self.enabled:
            return

        invalidate_folder_listing(bucket_name, folder_path)
        logger.debug(
            "Folder cache entry cleared for %s:%s",
            bucket_name,
            folder_path,
        )
        record_cache_event(
            event="folder_cache_invalidate",
            bucket=bucket_name,
            prefix=folder_path or "",
            hit=True,
            metadata={},
        )

    def invalidate_many(self, bucket_name: str, *folder_paths: Optional[str]) -> None:
        if not self.enabled:
            return
        if not folder_paths:
            self.invalidate(bucket_name)
            return
        invalidate_folder_listing_many(bucket_name, list(folder_paths))
        for path in folder_paths:
            record_cache_event(
                event="folder_cache_invalidate",
                bucket=bucket_name,
                prefix=path or "",
                hit=True,
                metadata={"batch": True},
            )
