"""Views for protected file downloads with ALTCHA verification."""

import json
import logging
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views import View

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.services.altcha_service import get_altcha_service
from lacos.storage.services.presigned_url_cache_service import get_presigned_url_cache_service
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.models.s3_resource_location import S3ResourceLocation

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Extract client IP from request for rate limiting."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def check_rate_limit(request, key_prefix: str, max_requests: int, window_seconds: int) -> bool:
    """Check if request is within rate limit.

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

    current_count = cache.get(cache_key, 0)
    if current_count >= max_requests:
        return False

    # Increment counter
    cache.set(cache_key, current_count + 1, timeout=window_seconds)
    return True


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
    import re
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
    """
    # Try to find the resource and its parent bundle for ACL check
    try:
        # Look up resource location to find associated bundle
        location = S3ResourceLocation.objects.filter(
            s3_bucket=bucket,
            s3_key=key
        ).first()

        if location and location.content_object:
            # If it's a bundle resource, check bundle ACL
            obj = location.content_object

            # Try to get the parent bundle
            bundle = None
            if isinstance(obj, Bundle):
                bundle = obj
            elif hasattr(obj, 'bundleresources_set'):
                # It's a resource, find the bundle
                bundle_resources = obj.bundleresources_set.first()
                if bundle_resources:
                    bundle = bundle_resources.bundle

            if bundle:
                acl_service = ACLEvaluationService()
                acl_result = acl_service.evaluate(request.user, bundle, mode="acl:Read")

                if not acl_result.allowed and acl_service.enforcement_enabled:
                    logger.warning(
                        f"ACL denied download for user {request.user} on {bucket}/{key}: {acl_result.reason}"
                    )
                    return "Access denied"

        # If no ACL record found, allow access (resource might be public or unmapped)
        return None

    except Exception as e:
        logger.error(f"Error checking authorization for {bucket}/{key}: {e}")
        # On error, deny access to be safe
        return "Authorization check failed"


class AltchaChallengeView(View):
    """Generate ALTCHA challenges for download protection."""

    # Rate limit: 30 challenges per minute per IP
    RATE_LIMIT_MAX = 30
    RATE_LIMIT_WINDOW = 60

    def get(self, request):
        """Return a new ALTCHA challenge."""
        # Rate limit challenge generation to prevent abuse
        if not check_rate_limit(
            request,
            'altcha_challenge',
            self.RATE_LIMIT_MAX,
            self.RATE_LIMIT_WINDOW
        ):
            logger.warning(f"Rate limit exceeded for ALTCHA challenges from {get_client_ip(request)}")
            return JsonResponse(
                {'error': 'Too many requests. Please try again later.'},
                status=429
            )

        service = get_altcha_service()
        challenge = service.create_challenge()
        return JsonResponse(challenge)


class ProtectedDownloadView(View):
    """
    Protected download endpoint that requires ALTCHA verification.

    Flow:
    1. Client solves ALTCHA challenge
    2. Client submits solution + resource info to this endpoint
    3. Server verifies solution and authorization
    4. Server returns presigned URL and curl command

    Note: CSRF is not required as this endpoint:
    - Requires ALTCHA proof-of-work (prevents automated attacks)
    - Only returns presigned URLs (no state modification)
    - Is designed for API/AJAX use from the download modal
    """

    def post(self, request):
        """Verify ALTCHA solution and return presigned download URL."""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Extract and validate ALTCHA solution
        altcha_payload = data.get('altcha')
        if not altcha_payload:
            return JsonResponse({'error': 'Missing ALTCHA solution'}, status=400)

        # Extract and validate resource info
        bucket = data.get('bucket', '').strip()
        key = data.get('key', '').strip()
        filename = data.get('filename')

        # Validate inputs
        validation_error = validate_bucket_key(bucket, key)
        if validation_error:
            return JsonResponse({'error': validation_error}, status=400)

        # Verify ALTCHA solution first (cheapest check)
        altcha_service = get_altcha_service()
        is_valid, error = altcha_service.verify_solution_base64(altcha_payload)

        if not is_valid:
            logger.warning(f"ALTCHA verification failed for {bucket}/{key}: {error}")
            return JsonResponse({
                'error': 'Verification failed',
                'detail': 'Please complete the verification again'
            }, status=403)

        # Check authorization
        auth_error = check_resource_authorization(request, bucket, key)
        if auth_error:
            return JsonResponse({
                'error': 'Access denied',
                'detail': 'You do not have permission to download this file'
            }, status=403)

        # Generate presigned URL
        url_service = get_presigned_url_cache_service()
        try:
            result = url_service.get_download_url(
                bucket=bucket,
                key=key,
                filename=filename
            )
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {bucket}/{key}: {e}")
            return JsonResponse({
                'error': 'Failed to generate download link',
                'detail': 'Please try again later'
            }, status=500)

        logger.info(f"Protected download authorized for {bucket}/{key} by user {request.user}")

        return JsonResponse({
            'success': True,
            'url': result['url'],
            'filename': result['filename'],
            'expires_in': result['expires_in'],
            'curl_command': result['curl_command']
        })


class BundleDownloadView(View):
    """
    Download multiple files from a bundle with ALTCHA protection.

    Returns presigned URLs for all requested resources.
    """

    # Maximum resources per request to prevent abuse
    MAX_RESOURCES = 100

    def post(self, request):
        """Verify ALTCHA and return presigned URLs for multiple resources."""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Extract and validate ALTCHA solution
        altcha_payload = data.get('altcha')
        if not altcha_payload:
            return JsonResponse({'error': 'Missing ALTCHA solution'}, status=400)

        # Extract and validate resources list
        resources = data.get('resources', [])
        if not resources:
            return JsonResponse({'error': 'No resources specified'}, status=400)

        if not isinstance(resources, list):
            return JsonResponse({'error': 'Resources must be a list'}, status=400)

        if len(resources) > self.MAX_RESOURCES:
            return JsonResponse({
                'error': f'Too many resources. Maximum is {self.MAX_RESOURCES}'
            }, status=400)

        # Verify ALTCHA solution first
        altcha_service = get_altcha_service()
        is_valid, error = altcha_service.verify_solution_base64(altcha_payload)

        if not is_valid:
            logger.warning(f"ALTCHA verification failed for bundle download: {error}")
            return JsonResponse({
                'error': 'Verification failed',
                'detail': 'Please complete the verification again'
            }, status=403)

        # Process each resource
        url_service = get_presigned_url_cache_service()
        downloads = []
        errors = []

        for i, resource in enumerate(resources):
            if not isinstance(resource, dict):
                errors.append({'index': i, 'error': 'Invalid resource format'})
                continue

            bucket = resource.get('bucket', '').strip() if resource.get('bucket') else ''
            key = resource.get('key', '').strip() if resource.get('key') else ''
            filename = resource.get('filename')

            # Validate inputs
            validation_error = validate_bucket_key(bucket, key)
            if validation_error:
                errors.append({'index': i, 'error': validation_error})
                continue

            # Check authorization
            auth_error = check_resource_authorization(request, bucket, key)
            if auth_error:
                errors.append({'index': i, 'error': 'Access denied', 'key': key})
                continue

            # Generate presigned URL
            try:
                result = url_service.get_download_url(
                    bucket=bucket,
                    key=key,
                    filename=filename
                )
                downloads.append(result)
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for {bucket}/{key}: {e}")
                errors.append({'index': i, 'error': 'Failed to generate link', 'key': key})

        logger.info(
            f"Protected bundle download: {len(downloads)} authorized, "
            f"{len(errors)} failed for user {request.user}"
        )

        response_data = {
            'success': len(downloads) > 0,
            'downloads': downloads,
            'count': len(downloads)
        }

        # Include errors if any occurred
        if errors:
            response_data['errors'] = errors

        return JsonResponse(response_data)
