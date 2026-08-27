"""Utility functions for protected file downloads."""

import logging
import re
from typing import Optional

from django.conf import settings

from lacos.common.cache_rate_limit import check_rate_limit as check_rate_limit
from lacos.common.request_utils import get_client_ip
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.exposure_policy_service import ExposurePolicyService

logger = logging.getLogger(__name__)


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
        If REQUIRE_S3_LOCATION_FOR_DOWNLOAD is False, access is still denied unless
        trusted server-side code sets request.allow_unmapped_s3_download=True.
    """
    require_location = getattr(settings, 'REQUIRE_S3_LOCATION_FOR_DOWNLOAD', True)

    def _has_explicit_unmapped_opt_in(req) -> bool:
        return getattr(req, 'allow_unmapped_s3_download', False) is True

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

        return None

    except Exception as e:
        logger.error("Error checking authorization", extra={"bucket": bucket, "key": key, "error": str(e)})
        # On error, deny access to be safe
        return "Authorization check failed"
