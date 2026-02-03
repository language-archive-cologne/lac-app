"""Service for caching presigned URLs to enable resumable downloads."""

import hashlib
import logging
import re
import shlex
import threading
from typing import Optional
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache

from .resource_mapping_service import ResourceMappingService

logger = logging.getLogger(__name__)


class PresignedUrlCacheService:
    """
    Caches presigned URLs to ensure the same URL is returned within the expiration window.

    This enables resumable downloads with curl -C - since the URL remains consistent.
    """

    CACHE_KEY_PREFIX = "presigned:download"
    CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
    SAFE_ASCII_CHARS = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- "
    )

    def __init__(self):
        self.resource_service = ResourceMappingService(skip_bucket_check=True)
        self.expiration = getattr(settings, 'PRESIGNED_URL_EXPIRATION', 86400)
        self.cache_buffer = getattr(settings, 'PRESIGNED_URL_CACHE_BUFFER', 300)
        self.cache_ttl = self.expiration - self.cache_buffer

    def _build_cache_key(
        self,
        bucket: str,
        key: str,
        response_headers: Optional[dict] = None,
        auth_context: Optional[str] = None,
    ) -> str:
        """Build a unique cache key for the presigned URL.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional response headers (affects URL signature)
            auth_context: Optional authorization context (user ID or permission hash)

        Returns:
            Cache key string
        """
        # Include response headers in cache key since they affect the presigned URL
        headers_hash = ""
        if response_headers:
            headers_str = str(sorted(response_headers.items()))
            headers_hash = hashlib.sha256(headers_str.encode()).hexdigest()

        auth_hash = ""
        if auth_context:
            auth_hash = hashlib.sha256(str(auth_context).encode()).hexdigest()

        # Create a safe cache key
        key_hash = hashlib.md5(f"{bucket}:{key}".encode()).hexdigest()

        parts = [self.CACHE_KEY_PREFIX, key_hash]
        if headers_hash:
            parts.append(headers_hash)
        if auth_hash:
            parts.append(auth_hash)
        return ":".join(parts)

    def _has_control_chars(self, value: str) -> bool:
        return bool(self.CONTROL_CHARS_RE.search(value))

    def _truncate_filename(self, filename: str, max_length: int) -> str:
        if len(filename) <= max_length:
            return filename
        base, dot, ext = filename.rpartition(".")
        if dot and len(ext) < max_length - 1:
            keep = max_length - len(ext) - 1
            return f"{base[:keep]}.{ext}"
        return filename[:max_length]

    def _sanitize_filename(self, filename: Optional[str], fallback: str) -> str:
        original = filename or ""
        candidate = str(filename).strip() if filename is not None else ""
        if not candidate:
            candidate = fallback

        candidate = candidate.replace("\\", "/").split("/")[-1]

        if self._has_control_chars(candidate):
            logger.warning(
                "Rejected download filename with control characters; using fallback "
                f"(filename={original!r})"
            )
            candidate = fallback.replace("\\", "/").split("/")[-1]

        candidate = self.CONTROL_CHARS_RE.sub("", candidate)
        candidate = (
            candidate.replace('"', "_")
            .replace("'", "_")
            .replace("\\", "_")
            .replace("/", "_")
            .replace("\r", "")
            .replace("\n", "")
            .replace("\x00", "")
        )
        candidate = candidate.strip()
        if not candidate:
            candidate = "download"

        candidate = self._truncate_filename(candidate, 255)
        return candidate

    def _ascii_fallback(self, filename: str) -> str:
        ascii_filename = filename.encode("ascii", "ignore").decode("ascii")
        ascii_filename = "".join(
            ch if ch in self.SAFE_ASCII_CHARS else "_" for ch in ascii_filename
        ).strip()
        if not ascii_filename:
            ascii_filename = "download"
        return self._truncate_filename(ascii_filename, 255)

    def get_presigned_url(
        self,
        bucket: str,
        key: str,
        response_headers: Optional[dict] = None,
        auth_context: Optional[str] = None,
        force_refresh: bool = False
    ) -> str:
        """Get a presigned URL, returning cached version if available.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional dict with response headers (Content-Disposition, etc.)
            auth_context: Optional authorization context for cache scoping
            force_refresh: If True, bypass cache and generate a new URL

        Returns:
            Presigned URL for GET access to the object
        """
        cache_key = self._build_cache_key(
            bucket, key, response_headers, auth_context
        )

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_url = cache.get(cache_key)
            if cached_url:
                logger.debug(f"Cache hit for presigned URL: {cache_key}")
                return cached_url

        # Generate new presigned URL
        logger.debug(f"Cache miss for presigned URL: {cache_key}, generating new URL")
        url = self.resource_service.generate_presigned_url(
            bucket=bucket,
            key=key,
            expires_in=self.expiration,
            response_headers=response_headers
        )

        # Cache the URL
        cache.set(cache_key, url, timeout=self.cache_ttl)
        logger.info(f"Cached presigned URL for {bucket}/{key} (TTL: {self.cache_ttl}s)")

        return url

    def get_download_url(
        self,
        bucket: str,
        key: str,
        filename: Optional[str] = None,
        auth_context: Optional[str] = None,
        force_refresh: bool = False
    ) -> dict:
        """Get a presigned download URL with Content-Disposition header.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            filename: Filename for Content-Disposition header (defaults to key basename)
            auth_context: Optional authorization context for cache scoping
            force_refresh: If True, bypass cache and generate a new URL

        Returns:
            Dict with 'url', 'filename', 'expires_in', and 'curl_command'
        """
        fallback_name = key.split('/')[-1] or 'download'
        sanitized_filename = self._sanitize_filename(filename, fallback=fallback_name)
        ascii_filename = self._ascii_fallback(sanitized_filename)

        # Build Content-Disposition with RFC 5987 encoding for non-ASCII filenames
        disposition = f'attachment; filename="{ascii_filename}"'
        if ascii_filename != sanitized_filename:
            # Add RFC 5987 encoded filename for non-ASCII characters
            encoded_filename = quote(sanitized_filename, safe='')
            disposition += f"; filename*=UTF-8''{encoded_filename}"

        response_headers = {
            'ResponseContentDisposition': disposition
        }

        url = self.get_presigned_url(
            bucket=bucket,
            key=key,
            response_headers=response_headers,
            auth_context=auth_context,
            force_refresh=force_refresh
        )

        # Build curl command with proper escaping for shell safety
        safe_filename = shlex.quote(sanitized_filename)
        safe_url = shlex.quote(url)
        curl_command = f'curl -C - -o {safe_filename} {safe_url}'

        return {
            'url': url,
            'filename': sanitized_filename,
            'expires_in': self.expiration,
            'curl_command': curl_command
        }

    def invalidate(
        self,
        bucket: str,
        key: str,
        response_headers: Optional[dict] = None,
        auth_context: Optional[str] = None,
    ):
        """Invalidate a cached presigned URL.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional response headers used when caching
        """
        cache_key = self._build_cache_key(
            bucket, key, response_headers, auth_context
        )
        cache.delete(cache_key)
        logger.info(f"Invalidated cached presigned URL: {cache_key}")


# Thread-safe singleton instance
_service_instance = None
_service_lock = threading.Lock()


def get_presigned_url_cache_service() -> PresignedUrlCacheService:
    """Get the singleton PresignedUrlCacheService instance (thread-safe)."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            # Double-check locking pattern
            if _service_instance is None:
                _service_instance = PresignedUrlCacheService()
    return _service_instance
