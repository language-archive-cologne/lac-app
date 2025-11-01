"""Coordinator mixin to persist and retrieve the active workspace bucket."""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


class BucketCoordinatorMixin:
    """Provide helper methods for keeping track of the active workspace bucket."""

    active_bucket_session_key = "storage_active_bucket"

    def _normalize_bucket_sequence(self, buckets: Optional[Sequence[str]]) -> List[str]:
        """Return a normalized list for any sequence of bucket names."""
        if not buckets:
            return []
        return list(dict.fromkeys([bucket for bucket in buckets if bucket]))

    def _fetch_workspace_buckets(self, request, workspace_buckets: Optional[Sequence[str]] = None) -> List[str]:
        """Return workspace buckets, populating from the service if needed."""
        if workspace_buckets is not None:
            return self._normalize_bucket_sequence(workspace_buckets)

        from lacos.storage.services.registry import get_bucket_service  # Lazy import to avoid circular deps

        buckets = get_bucket_service().get_all_accessible_buckets()
        return self._normalize_bucket_sequence(buckets)

    def ensure_active_bucket(self, request, workspace_buckets: Optional[Sequence[str]] = None) -> Optional[str]:
        """Ensure an active bucket exists in the session and return it."""
        buckets = self._fetch_workspace_buckets(request, workspace_buckets)

        if not buckets:
            logger.debug("BucketCoordinatorMixin.ensure_active_bucket called with no buckets available")
            self.clear_active_bucket(request)
            return None

        active_bucket = request.session.get(self.active_bucket_session_key)
        if active_bucket in buckets:
            return active_bucket

        active_bucket = buckets[0]
        request.session[self.active_bucket_session_key] = active_bucket
        logger.debug("Active bucket set to '%s' (ensure)", active_bucket)
        return active_bucket

    def get_active_bucket(self, request, workspace_buckets: Optional[Sequence[str]] = None) -> Optional[str]:
        """Return the active bucket stored in session (or establish one)."""
        active_bucket = request.session.get(self.active_bucket_session_key)
        if active_bucket:
            buckets = self._fetch_workspace_buckets(request, workspace_buckets)
            if active_bucket in buckets:
                return active_bucket

        return self.ensure_active_bucket(request, workspace_buckets)

    def set_active_bucket(self, request, bucket_name: Optional[str], workspace_buckets: Optional[Sequence[str]] = None) -> Optional[str]:
        """Persist the provided bucket as active when it is accessible."""
        buckets = self._fetch_workspace_buckets(request, workspace_buckets)

        if bucket_name and bucket_name in buckets:
            request.session[self.active_bucket_session_key] = bucket_name
            logger.debug("Active bucket updated to '%s' (set)", bucket_name)
            return bucket_name

        logger.debug(
            "Failed to set active bucket to '%s'; falling back via ensure_active_bucket", bucket_name
        )
        return self.ensure_active_bucket(request, buckets)

    def clear_active_bucket(self, request) -> None:
        """Remove any stored active bucket from the session."""
        if self.active_bucket_session_key in request.session:
            logger.debug("Clearing active bucket '%s' from session", request.session[self.active_bucket_session_key])
            del request.session[self.active_bucket_session_key]


__all__ = ["BucketCoordinatorMixin"]
