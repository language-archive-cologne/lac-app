"""Views for protected file downloads with ALTCHA verification."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views import View

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.services.altcha_service import get_altcha_service
from lacos.storage.services.presigned_url_cache_service import get_presigned_url_cache_service
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.resource_resolver_service import ResourceResolverService, ResolvedResource
from lacos.storage.services.download_script_service import DownloadScriptService, DownloadInfo
from lacos.storage.models.s3_resource_location import S3ResourceLocation

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
                logger.warning(f"Rate limit cache race for {cache_key}")
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

    Security:
        By default (REQUIRE_S3_LOCATION_FOR_DOWNLOAD=True), this function DENIES
        access unless an S3ResourceLocation record exists for the bucket/key.
        This prevents attackers from requesting presigned URLs for arbitrary S3 paths.
    """
    require_location = getattr(settings, 'REQUIRE_S3_LOCATION_FOR_DOWNLOAD', True)

    try:
        # Look up resource location to find associated bundle
        location = S3ResourceLocation.objects.filter(
            s3_bucket=bucket,
            s3_key=key
        ).first()

        # If no location record exists, deny by default (security)
        if not location:
            if require_location:
                logger.warning(
                    f"Download denied: no S3ResourceLocation for {bucket}/{key}"
                )
                return "Resource not found"
            # Legacy mode: allow unmapped resources (INSECURE)
            logger.warning(
                f"Allowing download of unmapped resource {bucket}/{key} "
                "(REQUIRE_S3_LOCATION_FOR_DOWNLOAD=False)"
            )
            return None

        # Location exists - check if it has a content object for ACL evaluation
        if location.content_object:
            obj = location.content_object

            # Try to get the parent bundle for ACL check
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

        # Location exists but no bundle association - resource is public
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


class BundleScriptDownloadView(View):
    """Generate download scripts for multiple bundle resources."""

    MAX_RESOURCES = 100
    RATE_LIMIT_MAX = 10  # 10 script generations per minute
    RATE_LIMIT_WINDOW = 60

    VALID_FORMATS = {"all", "bash", "powershell", "manifest"}

    def post(self, request):
        """Generate download scripts for bundle resources."""
        # 1. Rate limit check
        if not check_rate_limit(
            request,
            'bundle_script',
            self.RATE_LIMIT_MAX,
            self.RATE_LIMIT_WINDOW
        ):
            logger.warning(
                f"Rate limit exceeded for script generation from {get_client_ip(request)}"
            )
            return JsonResponse(
                {'error': 'Too many requests. Please try again later.'},
                status=429
            )

        # 2. Parse JSON body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        altcha_payload = data.get('altcha')
        bundle_id = data.get('bundle_id')
        resource_ids = data.get('resource_ids', [])
        script_format = data.get('format', 'all')

        # 3. Validate format
        if script_format not in self.VALID_FORMATS:
            return JsonResponse({
                'error': f'Invalid format. Must be one of: {", ".join(sorted(self.VALID_FORMATS))}'
            }, status=400)

        # Validate required fields
        if not altcha_payload:
            return JsonResponse({'error': 'Missing ALTCHA solution'}, status=400)

        if not bundle_id:
            return JsonResponse({'error': 'Missing bundle_id'}, status=400)

        if not isinstance(resource_ids, list):
            return JsonResponse({'error': 'resource_ids must be a list'}, status=400)

        # 4. Verify ALTCHA solution
        altcha_service = get_altcha_service()
        is_valid, error = altcha_service.verify_solution_base64(altcha_payload)

        if not is_valid:
            logger.warning(f"ALTCHA verification failed for script generation: {error}")
            return JsonResponse({
                'error': 'Verification failed',
                'detail': 'Please complete the verification again'
            }, status=403)

        # 5. Check resource count
        if len(resource_ids) > self.MAX_RESOURCES:
            return JsonResponse({
                'error': f'Too many resources. Maximum is {self.MAX_RESOURCES}'
            }, status=400)

        # Handle empty resource_ids gracefully
        if not resource_ids:
            return JsonResponse({
                'success': True,
                'bundle_name': '',
                'expires_at': None,
                'scripts': {},
                'file_count': 0,
                'total_size': 0,
                'errors': []
            })

        # 6. Call ResourceResolverService
        resolver = ResourceResolverService()
        resolved, errors = resolver.resolve_resources(
            bundle_id=bundle_id,
            resource_ids=resource_ids,
            user=request.user,
        )

        # Check for bundle_not_found error (all errors will have this)
        if errors and all(e.error == 'bundle_not_found' for e in errors):
            return JsonResponse({
                'success': False,
                'error': f'Bundle {bundle_id} not found'
            }, status=404)

        # Check for access_denied error (all errors will have this)
        if errors and all(e.error == 'access_denied' for e in errors):
            return JsonResponse({
                'success': False,
                'error': 'Access denied to bundle resources'
            }, status=403)

        # Get bundle name
        bundle_name = ''
        try:
            bundle = Bundle.objects.get(id=bundle_id)
            general_info = bundle.get_general_info
            if general_info:
                bundle_name = general_info.display_title or general_info.title or ''
            bundle_name = bundle_name or bundle.identifier or str(bundle_id)
        except Bundle.DoesNotExist:
            bundle_name = str(bundle_id)

        # 7. Convert ResolvedResource to DownloadInfo (sanitize filenames)
        script_service = DownloadScriptService()
        existing_filenames: set[str] = set()
        download_infos: list[DownloadInfo] = []

        for res in resolved:
            sanitized_filename = script_service.sanitize_filename(
                res.filename, existing_filenames
            )
            download_infos.append(DownloadInfo(
                filename=sanitized_filename,
                url=res.presigned_url,
                size=res.size,
                checksum=res.checksum,
                original_key=res.key,
            ))

        # Calculate expires_at from settings
        expiration_seconds = getattr(settings, 'PRESIGNED_URL_EXPIRATION', 86400)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiration_seconds)

        # 8. Generate scripts based on format
        scripts = {}

        if script_format in ('all', 'bash'):
            scripts['bash'] = script_service.generate_bash_script(
                download_infos, bundle_name, expires_at
            )

        if script_format in ('all', 'powershell'):
            scripts['powershell'] = script_service.generate_powershell_script(
                download_infos, bundle_name, expires_at
            )

        if script_format in ('all', 'manifest'):
            scripts['manifest'] = script_service.generate_manifest(
                download_infos, bundle_name, expires_at
            )

        # Calculate total size
        total_size = sum(dl.size for dl in download_infos)

        # Convert errors to serializable format
        error_list = [
            {'resource_id': e.resource_id, 'error': e.error, 'message': e.message}
            for e in errors
        ]

        logger.info(
            f"Script generation for bundle {bundle_id}: {len(resolved)} resolved, "
            f"{len(errors)} errors, format={script_format}, user={request.user}"
        )

        # 9. Return JSON response
        return JsonResponse({
            'success': True,
            'bundle_name': bundle_name,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'scripts': scripts,
            'file_count': len(download_infos),
            'total_size': total_size,
            'errors': error_list,
        })
