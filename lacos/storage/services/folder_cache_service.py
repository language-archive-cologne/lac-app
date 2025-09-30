"""Lightweight cache helper for bucket folder structures."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)


class FolderStructureCacheService:
    """Ad-hoc cache wrapper to store folder listings per bucket."""

    CACHE_PREFIX = "storage:structure"

    def __init__(self, timeout: int = 300) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize_path(self, folder_path: Optional[str]) -> str:
        if not folder_path:
            return "__root__"
        normalized = folder_path.strip('/')
        return normalized or "__root__"

    def _version_key(self, bucket_name: str) -> str:
        return f"{self.CACHE_PREFIX}:{bucket_name}:__v"

    def _compose_key(self, bucket_name: str, folder_path: Optional[str], version: int) -> str:
        normalized = self._normalize_path(folder_path)
        return f"{self.CACHE_PREFIX}:{bucket_name}:{version}:{normalized}"

    def _get_version(self, bucket_name: str) -> int:
        version_key = self._version_key(bucket_name)
        version = cache.get(version_key)
        if version is None:
            version = 1
            cache.set(version_key, version, timeout=None)
        return int(version)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(self, bucket_name: str, folder_path: Optional[str]) -> Optional[Any]:
        version = self._get_version(bucket_name)
        key = self._compose_key(bucket_name, folder_path, version)
        cached = cache.get(key)
        if cached is not None:
            logger.debug("Folder cache hit for %s:%s (v%s)", bucket_name, folder_path, version)
            return deepcopy(cached)
        return None

    def set(self, bucket_name: str, folder_path: Optional[str], value: Any) -> None:
        version = self._get_version(bucket_name)
        key = self._compose_key(bucket_name, folder_path, version)
        cache.set(key, deepcopy(value), timeout=self.timeout)
        logger.debug("Folder cache stored for %s:%s (v%s)", bucket_name, folder_path, version)

    def invalidate(self, bucket_name: str, folder_path: Optional[str] = None) -> None:
        if folder_path is None:
            version_key = self._version_key(bucket_name)
            try:
                cache.incr(version_key)
            except ValueError:
                cache.set(version_key, 2, timeout=None)
            logger.debug("Folder cache version bumped for bucket %s", bucket_name)
            return

        version = self._get_version(bucket_name)
        key = self._compose_key(bucket_name, folder_path, version)
        cache.delete(key)
        logger.debug("Folder cache entry cleared for %s:%s (v%s)", bucket_name, folder_path, version)

    def invalidate_many(self, bucket_name: str, *folder_paths: Optional[str]) -> None:
        if not folder_paths:
            self.invalidate(bucket_name)
            return
        for path in folder_paths:
            self.invalidate(bucket_name, path)
