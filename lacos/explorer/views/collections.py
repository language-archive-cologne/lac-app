"""Collection views for the explorer app."""

import json
import logging
from urllib.parse import unquote

from django.core.cache import cache
from django.db.models import Count, Min, Prefetch
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from lacos.blam.models import Collection
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.explorer.map_utils import get_collection_map_markers
from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type
from lacos.explorer.search import search_archives
from lacos.explorer.views.utils import build_content_disposition
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .utils import get_formatted_location, paginate_bundle_contexts, HandleLookupMixin, annotate_resource, get_object_by_pk_or_handle


logger = logging.getLogger(__name__)

LANGUAGE_COUNT_CACHE_KEY = "explorer:language_count"
LANGUAGE_COUNT_CACHE_TIMEOUT = 86400  # 24 hours (invalidated on collection changes)


class CollectionListView(ListView):
    model = Collection
    template_name = "collection_list.html"
    context_object_name = "collection_list"

    def get_queryset(self):
        """Explicitly return all collections and log the count."""
        logger.info("Fetching collections in CollectionListView...")
        queryset = Collection.objects.prefetch_related(
            Prefetch(
                'general_info',
                queryset=CollectionGeneralInfo.objects.select_related('location'),
                to_attr='prefetched_general_info',
            ),
            'general_info__object_languages',
            'publication_info',
            'publication_info__creators',
        ).annotate(
            bundles_count=Count('bundle_collection'),
            first_language=Min('general_info__object_languages__name'),
        )

        sort = self.request.GET.get('sort', 'name')
        order = self.request.GET.get('order', 'asc')
        prefix = '-' if order == 'desc' else ''

        if sort == 'language':
            queryset = queryset.order_by(f'{prefix}first_language', 'general_info__display_title')
        elif sort == 'bundles':
            queryset = queryset.order_by(f'{prefix}bundles_count', 'general_info__display_title')
        else:
            queryset = queryset.order_by(f'{prefix}general_info__display_title')

        collection_count = queryset.count()
        logger.info(f"Found {collection_count} collections.")
        return queryset

    def get_context_data(self, **kwargs):
        """Add processed location data to the context."""
        context = super().get_context_data(**kwargs)
        search_query = self.request.GET.get("q", "").strip()
        context["search_query"] = search_query
        if search_query:
            search_results = search_archives(search_query)
            context["search_results"] = search_results
            context["collection_search_results"] = [
                result for result in search_results if result.kind == "collection"
            ]
            context["bundle_search_results"] = [
                result for result in search_results if result.kind == "bundle"
            ]

        for collection in context['collection_list']:
            # Use prefetched data to avoid N+1 queries
            general_info_list = getattr(collection, 'prefetched_general_info', None)
            general_info = general_info_list[0] if general_info_list else None
            if general_info and general_info.location:
                location = general_info.location
                collection.formatted_location = get_formatted_location(location)
                collection.geo_location = location.geo_location
            else:
                collection.formatted_location = ""
                collection.geo_location = None

        context['map_markers_json'] = get_collection_map_markers(context['collection_list'])

        # Cache language count as it rarely changes
        languages_count = cache.get(LANGUAGE_COUNT_CACHE_KEY)
        if languages_count is None:
            languages_count = CollectionObjectLanguage.objects.values('name').distinct().count()
            cache.set(LANGUAGE_COUNT_CACHE_KEY, languages_count, LANGUAGE_COUNT_CACHE_TIMEOUT)

        context['stats'] = {
            'collections_count': (
                context['collection_list'].count()
                if hasattr(context['collection_list'], 'count')
                else len(context['collection_list'])
            ),
            'languages_count': languages_count,
        }

        context['current_sort'] = self.request.GET.get('sort', 'name')
        context['current_order'] = self.request.GET.get('order', 'asc')

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('HX-Request'):
            if 'q' in self.request.GET:
                return render(
                    self.request,
                    'explorer/partials/collection_search_results_content.html',
                    context,
                )
            if 'sort' in self.request.GET:
                return render(
                    self.request,
                    'explorer/partials/collections_table.html',
                    context,
                )
        return super().render_to_response(context, **response_kwargs)


class CollectionDetailView(HandleLookupMixin, DetailView):
    """Detail view for a collection, accessible by UUID or handle."""

    model = Collection
    template_name = "collection_detail.html"
    context_object_name = "collection"

    def get_queryset(self):
        return Collection.objects.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "publication_info",
            "publication_info__creators",
            "structural_info",
            "structural_info__additional_metadata_files",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
            self.object.geo_location = location.geo_location
        else:
            self.object.formatted_location = ""
            self.object.geo_location = None

        page_number = self.request.GET.get('bundle_page')
        bundle_search = self.request.GET.get('bundle_search', '').strip()
        context['bundle_search'] = bundle_search
        page_obj, bundle_contexts = paginate_bundle_contexts(
            self.object, page_number, search_query=bundle_search or None
        )

        query_params = self.request.GET.copy()
        if 'bundle_page' in query_params:
            query_params.pop('bundle_page')
        base_query = query_params.urlencode()
        if base_query:
            base_url = f"{self.request.path}?{base_query}"
        else:
            base_url = self.request.path
        separator = '&' if '?' in base_url else '?'

        context['bundle_page_obj'] = page_obj
        context['bundle_contexts'] = bundle_contexts
        context['bundle_page_base_url'] = base_url
        context['bundle_page_separator'] = separator
        context['bundles_total'] = page_obj.paginator.count if page_obj else 0

        acl_service = ACLEvaluationService()
        collection_acl = acl_service.evaluate(self.request.user, self.object)
        context['collection_acl_check_result'] = collection_acl
        context['collection_can_read'] = collection_acl.allowed or not acl_service.enforcement_enabled
        context['collection_acl_enforcement_enabled'] = acl_service.enforcement_enabled

        # Additional metadata files
        context['additional_metadata_files'] = []
        if hasattr(self.object, 'structural_info') and self.object.structural_info.first():
            metadata_files = [
                annotate_resource(res)
                for res in self.object.structural_info.first().additional_metadata_files.all()
            ]
            context['additional_metadata_files'] = [res for res in metadata_files if res]

        for bundle_info in bundle_contexts:
            bundle = bundle_info.get('bundle')
            if not bundle:
                continue
            bundle_acl = acl_service.evaluate(self.request.user, bundle)
            bundle_info['acl_check_result'] = bundle_acl
            bundle_info['access_level'] = bundle_acl.access_level
            bundle_info['can_read_bundle'] = bundle_acl.allowed or not acl_service.enforcement_enabled

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('HX-Request'):
            if 'bundle_page' in self.request.GET or 'bundle_search' in self.request.GET:
                return render(
                    self.request,
                    'explorer/partials/collection_bundles_table.html',
                    context,
                )
        return super().render_to_response(context, **response_kwargs)


class CollectionResourcesView(View):
    """View for accessing collection additional metadata files."""

    permission_denied_message = _("You do not have permission to access this collection.")

    def get(self, request, pk=None, handle=None, resource_id=None):
        collection = get_object_by_pk_or_handle(Collection, pk=pk, handle=handle)
        acl_service = ACLEvaluationService()
        acl_result = acl_service.evaluate(request.user, collection, mode="acl:Read")
        if acl_service.enforcement_enabled and not acl_result.allowed:
            return HttpResponseForbidden(self.permission_denied_message)

        if not resource_id:
            raise Http404("Resource ID required")

        action = request.GET.get('action', 'download')

        try:
            decoded_resource_id = unquote(resource_id)
            if decoded_resource_id.startswith('ID_'):
                decoded_resource_id = decoded_resource_id[3:]

            # Try to find the metadata file in the collection's additional metadata
            metadata_file = None
            structural_info = collection.structural_info.first()
            if structural_info:
                metadata_file = structural_info.additional_metadata_files.filter(
                    file_pid=decoded_resource_id
                ).first()

            resource_service = ResourceMappingService()
            location = resource_service.resolve_pid_to_s3(decoded_resource_id)
            if not location:
                raise ValueError(f"No S3 location found for PID: {decoded_resource_id}")

            # Get file information for display
            file_name = metadata_file.file_name if metadata_file else location.s3_key.split('/')[-1]
            file_description = metadata_file.file_description if metadata_file else ''
            mime_type = metadata_file.mime_type if metadata_file else 'application/octet-stream'

            detected_media_type = determine_media_type(mime_type, file_name)
            source_mime_type = guess_source_mime_type(mime_type, file_name, detected_media_type)

            # Generate presigned URL for streaming/preview
            presigned_url = resource_service.generate_presigned_url(
                location.s3_bucket,
                location.s3_key
            )

            # Generate download URL with proper content disposition
            download_headers = {
                'ResponseContentDisposition': build_content_disposition(file_name),
            }
            if source_mime_type:
                download_headers['ResponseContentType'] = source_mime_type

            download_url = resource_service.generate_presigned_url(
                location.s3_bucket,
                location.s3_key,
                response_headers=download_headers,
            )

            is_htmx = request.headers.get('HX-Request') == 'true'

            if is_htmx and action in {'play', 'view'}:
                return self._render_htmx_modal(
                    request, file_name, file_description, mime_type,
                    detected_media_type, source_mime_type, presigned_url, download_url
                )

            if action == 'download':
                return redirect(download_url)

            # Default: redirect to presigned URL
            return redirect(presigned_url)

        except ValueError as e:
            logger.error(f"Resource mapping service error: {e}")
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error(f"Error accessing resource: {e}")
            raise Http404(f"Error accessing resource: {str(e)}")

    def _render_htmx_modal(
        self, request, file_name, file_description, mime_type,
        detected_media_type, source_mime_type, presigned_url, download_url
    ):
        """Render the HTMX modal response for play/view actions."""
        modal_context = {
            'resource_name': file_name,
            'resource_description': file_description,
            'mime_type': mime_type,
            'media_type': detected_media_type,
            'source_mime_type': source_mime_type,
            'stream_url': presigned_url if detected_media_type in {'audio', 'video'} else None,
            'preview_url': presigned_url,
            'download_url': download_url,
            'elan_context': None,
        }

        response = render(
            request,
            'explorer/partials/resource_modal_content.html',
            modal_context,
        )
        response['HX-Trigger'] = json.dumps({'showResourceModal': True})
        return response
