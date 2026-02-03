"""Views for protected file downloads with ALTCHA verification."""

import json
import logging

from django.http import JsonResponse
from django.views import View

from lacos.storage.services.altcha_service import get_altcha_service
from lacos.storage.services.presigned_url_cache_service import get_presigned_url_cache_service
from lacos.storage.views.download_utils import (
    check_rate_limit,
    check_resource_authorization,
    get_client_ip,
    validate_bucket_key,
)

logger = logging.getLogger(__name__)


class AltchaChallengeView(View):
    """Generate ALTCHA challenges for download protection."""

    RATE_LIMIT_MAX = 30  # 30 challenges per minute per IP
    RATE_LIMIT_WINDOW = 60

    def get(self, request):
        """Return a new ALTCHA challenge."""
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

        auth_context = (
            f"user:{request.user.pk}"
            if getattr(request.user, "is_authenticated", False)
            else f"anon:{get_client_ip(request)}"
        )

        # Generate presigned URL
        url_service = get_presigned_url_cache_service()
        try:
            result = url_service.get_download_url(
                bucket=bucket,
                key=key,
                filename=filename,
                auth_context=auth_context,
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
        auth_context = (
            f"user:{request.user.pk}"
            if getattr(request.user, "is_authenticated", False)
            else f"anon:{get_client_ip(request)}"
        )

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
                    filename=filename,
                    auth_context=auth_context,
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

        if errors:
            response_data['errors'] = errors

        return JsonResponse(response_data)


# Re-export for backwards compatibility
from lacos.storage.views.script_download_views import BundleScriptDownloadView  # noqa: E402, F401
