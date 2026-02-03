"""Views for generating download scripts (bash, powershell, manifest)."""

import json
import logging
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.http import JsonResponse
from django.views import View

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.services.altcha_service import get_altcha_service
from lacos.storage.services.resource_resolver_service import ResourceResolverService, ResolvedResource
from lacos.storage.services.download_script_service import DownloadScriptService, DownloadInfo
from lacos.storage.views.download_utils import check_rate_limit, get_client_ip

logger = logging.getLogger(__name__)


class BundleScriptDownloadView(View):
    """Generate download scripts for bundle or collection resources."""

    MAX_RESOURCES = 100
    RATE_LIMIT_MAX = 10  # 10 script generations per minute
    RATE_LIMIT_WINDOW = 60

    VALID_FORMATS = {"all", "bash", "powershell", "manifest"}

    def post(self, request):
        """Generate download scripts for bundle or collection resources."""
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
        collection_id = data.get('collection_id')
        bundles = data.get('bundles')  # List of {bundle_id, resource_ids}
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

        # Must have either bundle_id, collection_id, or bundles array
        if not bundle_id and not collection_id and not bundles:
            return JsonResponse({'error': 'Missing bundle_id, collection_id, or bundles'}, status=400)

        # Validate bundles array if provided
        if bundles:
            if not isinstance(bundles, list):
                return JsonResponse({'error': 'bundles must be a list'}, status=400)
            for i, b in enumerate(bundles):
                if not isinstance(b, dict):
                    return JsonResponse({'error': f'bundles[{i}] must be an object'}, status=400)
                if not b.get('bundle_id'):
                    return JsonResponse({'error': f'bundles[{i}] missing bundle_id'}, status=400)
                if not isinstance(b.get('resource_ids', []), list):
                    return JsonResponse({'error': f'bundles[{i}].resource_ids must be a list'}, status=400)

        if not bundles and not isinstance(resource_ids, list):
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
        total_resource_count = len(resource_ids)
        if bundles:
            total_resource_count = sum(len(b.get('resource_ids', [])) for b in bundles)
        if total_resource_count > self.MAX_RESOURCES:
            return JsonResponse({
                'error': f'Too many resources. Maximum is {self.MAX_RESOURCES}'
            }, status=400)

        # Handle empty resources gracefully
        if not bundles and not resource_ids:
            return JsonResponse({
                'success': True,
                'bundle_name': '',
                'expires_at': None,
                'scripts': {},
                'file_count': 0,
                'total_size': 0,
                'errors': []
            })

        # 6. Resolve resources
        resolved, errors, entity_name = self._resolve_resources(
            request, data, bundles, bundle_id, collection_id, resource_ids
        )

        # Handle resolution errors
        error_response = self._check_resolution_errors(
            errors, resolved, bundle_id, collection_id, bundles
        )
        if error_response:
            return error_response

        # 7. Generate scripts
        is_multi_bundle = bundles is not None
        return self._generate_response(
            resolved, errors, entity_name, script_format, collection_id, is_multi_bundle
        )

    def _resolve_resources(self, request, data, bundles, bundle_id, collection_id, resource_ids):
        """Resolve resources from bundles or collection."""
        resolver = ResourceResolverService()
        resolved: list[ResolvedResource] = []
        errors = []
        entity_name = ''

        if bundles:
            # Multi-bundle mode: resolve resources from multiple bundles
            entity_name = data.get('entity_name', 'Selected Files')
            for bundle_entry in bundles:
                b_id = bundle_entry.get('bundle_id')
                b_resource_ids = bundle_entry.get('resource_ids', [])
                if not b_resource_ids:
                    continue
                b_resolved, b_errors = resolver.resolve_resources(
                    bundle_id=b_id,
                    resource_ids=b_resource_ids,
                    user=request.user,
                )
                resolved.extend(b_resolved)
                errors.extend(b_errors)
        elif collection_id:
            resolved, errors = resolver.resolve_collection_resources(
                collection_id=collection_id,
                resource_ids=resource_ids,
                user=request.user,
            )
            entity_name = self._get_collection_name(collection_id)
        else:
            resolved, errors = resolver.resolve_resources(
                bundle_id=bundle_id,
                resource_ids=resource_ids,
                user=request.user,
            )
            entity_name = self._get_bundle_name(bundle_id)

        return resolved, errors, entity_name

    def _get_bundle_name(self, bundle_id: str) -> str:
        """Get display name for a bundle."""
        try:
            bundle = Bundle.objects.get(id=bundle_id)
            general_info = bundle.get_general_info
            if general_info:
                name = general_info.display_title or general_info.title or ''
                if name:
                    return name
            return bundle.identifier or str(bundle_id)
        except (Bundle.DoesNotExist, ValueError):
            return str(bundle_id)

    def _get_collection_name(self, collection_id: str) -> str:
        """Get display name for a collection."""
        try:
            from lacos.blam.models.collection.collection_repository import Collection
            collection = Collection.objects.get(id=collection_id)
            general_info = collection.get_general_info
            if general_info:
                name = general_info.display_title or general_info.title or ''
                if name:
                    return name
            return collection.identifier or str(collection_id)
        except Exception:
            return str(collection_id)

    def _check_resolution_errors(self, errors, resolved, bundle_id, collection_id, bundles):
        """Check for fatal resolution errors and return appropriate response.

        Only returns an error response if ALL resources failed to resolve.
        If some resources resolved successfully, we allow partial success.
        """
        if not errors:
            return None

        # If we have some resolved resources, allow partial success
        if resolved:
            return None

        # All resources failed - check for specific error types
        if all(e.error == 'collection_not_found' for e in errors):
            return JsonResponse({
                'success': False,
                'error': f'Collection {collection_id} not found'
            }, status=404)

        if all(e.error == 'bundle_not_found' for e in errors):
            # In multi-bundle mode, extract bundle IDs from the request bundles list
            if bundles:
                failed_bundle_ids = [b.get('bundle_id') for b in bundles]
                return JsonResponse({
                    'success': False,
                    'error': f'Bundles not found: {", ".join(str(bid) for bid in failed_bundle_ids)}'
                }, status=404)
            return JsonResponse({
                'success': False,
                'error': f'Bundle {bundle_id} not found'
            }, status=404)

        # Check for access_denied errors
        if all(e.error == 'access_denied' for e in errors):
            return JsonResponse({
                'success': False,
                'error': 'Access denied to resources'
            }, status=403)

        # All resources failed with mixed error types - return generic error
        return JsonResponse({
            'success': False,
            'error': 'All requested resources could not be resolved'
        }, status=400)

    def _generate_response(
        self, resolved, errors, entity_name, script_format, collection_id, is_multi_bundle=False
    ):
        """Generate scripts and build response."""
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

        # Generate scripts based on format
        scripts = {}
        if script_format in ('all', 'bash'):
            scripts['bash'] = script_service.generate_bash_script(
                download_infos, entity_name, expires_at
            )
        if script_format in ('all', 'powershell'):
            scripts['powershell'] = script_service.generate_powershell_script(
                download_infos, entity_name, expires_at
            )
        if script_format in ('all', 'manifest'):
            scripts['manifest'] = script_service.generate_manifest(
                download_infos, entity_name, expires_at
            )

        total_size = sum(dl.size for dl in download_infos)
        error_list = [
            {'resource_id': e.resource_id, 'error': e.error, 'message': e.message}
            for e in errors
        ]

        # Determine entity type for logging
        if is_multi_bundle:
            entity_type = 'multi-bundle'
        elif collection_id:
            entity_type = 'collection'
        else:
            entity_type = 'bundle'
        logger.info(
            f"Script generation for {entity_type}: {len(resolved)} resolved, "
            f"{len(errors)} errors, format={script_format}"
        )

        return JsonResponse({
            'success': True,
            'bundle_name': entity_name,
            'expires_at': expires_at.isoformat().replace('+00:00', 'Z'),
            'scripts': scripts,
            'file_count': len(download_infos),
            'total_size': total_size,
            'errors': error_list,
        })
