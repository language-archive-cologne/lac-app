"""Utility functions for protected file downloads."""

import logging
import re
from typing import Optional

from django.conf import settings
from django.core.cache import cache

from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.blam.models.bundle.bundle_repository import Bundle

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Extract client IP from request for rate limiting.

    Only trusts X-Forwarded-For header if the request came from a trusted proxy.
    Configure TRUSTED_PROXY_IPS in Django settings as a list of IP addresses.
    If not configured or empty, falls back to REMOTE_ADDR only (secure default).
    """
    remote_addr = request.META.get('REMOTE_ADDR', 'unknown')

    # Get trusted proxy list from settings
    trusted_proxies = getattr(settings, 'TRUSTED_PROXY_IPS', None)

    # Only trust X-Forwarded-For if request came from a trusted proxy
    if trusted_proxies and remote_addr in trusted_proxies:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Return the first (client) IP from the chain
            return x_forwarded_for.split(',')[0].strip()

    return remote_addr


def check_rate_limit(request, key_prefix: str, max_requests: int, window_seconds: int) -> bool:
    """Check if request is within rate limit.

    Uses atomic cache operations to prevent race conditions under concurrent requests.

    Args:
        request: Django request object
        key_prefix: Cache key prefix for this rate limit
        max_requests: Maximum requests allowed in window
        window_seconds: Time window in seconds

    Returns:
        True if request is allowed, False if rate limited
    """
    client_ip = get_client_ip(request)
    cache_key = f"ratelimit:{key_prefix}:{client_ip}"

    try:
        # Try to increment existing key atomically
        new_count = cache.incr(cache_key)
    except ValueError:
        # Key doesn't exist, create it atomically with add()
        # add() only sets if key doesn't exist, preventing race conditions
        added = cache.add(cache_key, 1, timeout=window_seconds)
        if added:
            new_count = 1
        else:
            # Another request created the key between our incr and add
            # Try increment again
            try:
                new_count = cache.incr(cache_key)
            except ValueError:
                # Extremely rare: key expired between add failure and this incr
                # Allow request but log for monitoring
                logger.warning("Rate limit cache race", extra={"cache_key": cache_key})
                return True

    return new_count <= max_requests


def validate_bucket_key(bucket: str, key: str) -> Optional[str]:
    """Validate bucket and key to prevent path traversal and injection.

    Returns:
        Error message if invalid, None if valid.
    """
    if not bucket or not key:
        return "Missing bucket or key"

    # Prevent path traversal
    if '..' in bucket or '..' in key:
        return "Invalid path"

    # Basic validation
    if len(bucket) > 255 or len(key) > 1024:
        return "Path too long"

    # Only allow alphanumeric, dash, underscore, slash, dot in paths
    if not re.match(r'^[a-zA-Z0-9\-_]+$', bucket):
        return "Invalid bucket name"

    if not re.match(r'^[a-zA-Z0-9\-_./]+$', key):
        return "Invalid key format"

    return None


def check_resource_authorization(request, bucket: str, key: str) -> Optional[str]:
    """Check if user is authorized to access the resource.

    Args:
        request: Django request object
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        Error message if not authorized, None if authorized.

    Security:
        By default (REQUIRE_S3_LOCATION_FOR_DOWNLOAD=True), this function DENIES
        access unless an S3ResourceLocation record exists for the bucket/key.
        This prevents attackers from requesting presigned URLs for arbitrary S3 paths.
        If REQUIRE_S3_LOCATION_FOR_DOWNLOAD is False, access is still denied unless the
        request explicitly opts in (X-Allow-Unmapped-S3-Download: true or
        request.allow_unmapped_s3_download=True).
    """
    require_location = getattr(settings, 'REQUIRE_S3_LOCATION_FOR_DOWNLOAD', True)

    def _has_explicit_unmapped_opt_in(req) -> bool:
        if getattr(req, 'allow_unmapped_s3_download', False):
            return True
        header_value = req.META.get('HTTP_X_ALLOW_UNMAPPED_S3_DOWNLOAD', '')
        return str(header_value).strip().lower() in {'1', 'true', 'yes'}

    try:
        policy = ExposurePolicyService()
        # Look up resource location to find associated bundle
        location = S3ResourceLocation.objects.filter(
            s3_bucket=bucket,
            s3_key=key
        ).first()

        # If no location record exists, deny by default (security)
        if not location:
            if require_location:
                logger.warning(
                    "Download denied: no S3ResourceLocation found",
                    extra={"bucket": bucket, "key": key},
                )
                return "Resource not found"
            # Legacy mode is disabled unless explicitly opted in per request.
            if not _has_explicit_unmapped_opt_in(request):
                logger.error(
                    "Download denied: REQUIRE_S3_LOCATION_FOR_DOWNLOAD=False without explicit opt-in",
                    extra={"bucket": bucket, "key": key, "user": str(request.user), "ip": get_client_ip(request)},
                )
                return "Resource not found"
            logger.error(
                "SECURITY WARNING: allowing download of unmapped resource via explicit opt-in",
                extra={"bucket": bucket, "key": key, "user": str(request.user), "ip": get_client_ip(request)},
            )
            return None

        if not policy.can_download_binary(request.user, location):
            logger.warning(
                "Exposure policy denied download",
                extra={"user": str(request.user), "bucket": bucket, "key": key},
            )
            return "Access denied"

        # Preserve explicit ACL logging for protected bundle resources.
        obj = location.content_object
        if isinstance(obj, Bundle):
            bundle = obj
        elif hasattr(obj, 'bundleresources_set'):
            bundle_resources = obj.bundleresources_set.first()
            bundle = bundle_resources.bundle if bundle_resources else None
        else:
            bundle = None

        if bundle:
            acl_service = ACLEvaluationService()
            acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")
            if not acl_result.allowed and acl_service.enforcement_enabled:
                logger.warning(
                    "ACL denied download",
                    extra={"user": str(request.user), "bucket": bucket, "key": key, "reason": acl_result.reason},
                )
                return "Access denied"

        return None

    except Exception as e:
        logger.error("Error checking authorization", extra={"bucket": bucket, "key": key, "error": str(e)})
        # On error, deny access to be safe
        return "Authorization check failed"
