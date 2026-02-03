"""Service for caching presigned URLs to enable resumable downloads."""

import hashlib
import logging
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

    def __init__(self):
        self.resource_service = ResourceMappingService(skip_bucket_check=True)
        self.expiration = getattr(settings, 'PRESIGNED_URL_EXPIRATION', 86400)
        self.cache_buffer = getattr(settings, 'PRESIGNED_URL_CACHE_BUFFER', 300)
        self.cache_ttl = self.expiration - self.cache_buffer

    def _build_cache_key(
        self,
        bucket: str,
        key: str,
        response_headers: Optional[dict] = None
    ) -> str:
        """Build a unique cache key for the presigned URL.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional response headers (affects URL signature)

        Returns:
            Cache key string
        """
        # Include response headers in cache key since they affect the presigned URL
        headers_hash = ""
        if response_headers:
            headers_str = str(sorted(response_headers.items()))
            headers_hash = hashlib.md5(headers_str.encode()).hexdigest()[:8]

        # Create a safe cache key
        key_hash = hashlib.md5(f"{bucket}:{key}".encode()).hexdigest()

        if headers_hash:
            return f"{self.CACHE_KEY_PREFIX}:{key_hash}:{headers_hash}"
        return f"{self.CACHE_KEY_PREFIX}:{key_hash}"

    def get_presigned_url(
        self,
        bucket: str,
        key: str,
        response_headers: Optional[dict] = None,
        force_refresh: bool = False
    ) -> str:
        """Get a presigned URL, returning cached version if available.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional dict with response headers (Content-Disposition, etc.)
            force_refresh: If True, bypass cache and generate a new URL

        Returns:
            Presigned URL for GET access to the object
        """
        cache_key = self._build_cache_key(bucket, key, response_headers)

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
        force_refresh: bool = False
    ) -> dict:
        """Get a presigned download URL with Content-Disposition header.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            filename: Filename for Content-Disposition header (defaults to key basename)
            force_refresh: If True, bypass cache and generate a new URL

        Returns:
            Dict with 'url', 'filename', 'expires_in', and 'curl_command'
        """
        if filename is None:
            filename = key.split('/')[-1]

        # Build Content-Disposition with RFC 5987 encoding for non-ASCII filenames
        ascii_filename = filename.encode('ascii', 'ignore').decode('ascii') or 'download'
        disposition = f'attachment; filename="{ascii_filename}"'
        if ascii_filename != filename:
            # Add RFC 5987 encoded filename for non-ASCII characters
            encoded_filename = quote(filename, safe='')
            disposition += f"; filename*=UTF-8''{encoded_filename}"

        response_headers = {
            'ResponseContentDisposition': disposition
        }

        url = self.get_presigned_url(
            bucket=bucket,
            key=key,
            response_headers=response_headers,
            force_refresh=force_refresh
        )

        # Build curl command with proper escaping for shell safety
        safe_filename = shlex.quote(filename)
        safe_url = shlex.quote(url)
        curl_command = f'curl -C - -o {safe_filename} {safe_url}'

        return {
            'url': url,
            'filename': filename,
            'expires_in': self.expiration,
            'curl_command': curl_command
        }

    def invalidate(self, bucket: str, key: str, response_headers: Optional[dict] = None):
        """Invalidate a cached presigned URL.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            response_headers: Optional response headers used when caching
        """
        cache_key = self._build_cache_key(bucket, key, response_headers)
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
