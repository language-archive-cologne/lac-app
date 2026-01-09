"""Collection views for the explorer app."""

import logging

from django.db.models import Count, Min
from django.shortcuts import render
from django.views.generic import DetailView, ListView

from lacos.blam.models import Collection
from lacos.blam.models.collection.collection_general_info import CollectionObjectLanguage
from lacos.explorer.map_utils import get_collection_map_markers
from lacos.explorer.search import search_archives
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService

from .utils import get_formatted_location, paginate_bundle_contexts


logger = logging.getLogger(__name__)


class CollectionListView(ListView):
    model = Collection
    template_name = "collection_list.html"
    context_object_name = "collection_list"

    def get_queryset(self):
        """Explicitly return all collections and log the count."""
        logger.info("Fetching collections in CollectionListView...")
        queryset = Collection.objects.annotate(
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
            if collection.get_general_info and collection.get_general_info.location:
                location = collection.get_general_info.location
                collection.formatted_location = get_formatted_location(location)
                collection.geo_location = location.geo_location
            else:
                collection.formatted_location = ""
                collection.geo_location = None

        context['map_markers_json'] = get_collection_map_markers(context['collection_list'])

        context['stats'] = {
            'collections_count': (
                context['collection_list'].count()
                if hasattr(context['collection_list'], 'count')
                else len(context['collection_list'])
            ),
            'languages_count': CollectionObjectLanguage.objects.values('name').distinct().count(),
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


class CollectionDetailView(DetailView):
    model = Collection
    template_name = "collection_detail.html"
    context_object_name = "collection"

    def get_queryset(self):
        return Collection.objects.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "publication_info",
            "publication_info__creators",
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
