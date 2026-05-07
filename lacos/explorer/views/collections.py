"""Collection views for the explorer app."""

import json
import logging
from urllib.parse import unquote

from django.conf import settings
from django.core.cache import cache
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Min, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from django.http import JsonResponse

from lacos.blam.models import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.mappers.collection.write.collection_exporter import CollectionExporter
from lacos.blam.serializers import CollectionJsonLdSerializer
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.explorer.glottolog import lookup_glottolog_entry
from lacos.explorer.map_utils import get_collection_map_markers
from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type
from lacos.explorer.permissions import (
    ACLPermissionMixin,
    MetadataExposureMixin,
    enforce_binary_exposure,
)
from lacos.explorer.search import search_archives
from lacos.explorer.views.utils import build_content_disposition
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.exposure_policy_service import ExposurePolicyService
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.media_processing_service import MediaProcessingService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

from .utils import (
    HandleLookupMixin,
    annotate_resource,
    get_formatted_location,
    get_object_by_pk_or_handle,
    is_imdi_resource,
    load_markdown_preview,
    load_xml_preview,
    paginate_bundle_contexts,
    resolve_collection_metadata_to_presigned,
    render_imdi_modal_response,
    find_subtitle_for_collection_video,
    summarize_bundle_access_levels_by_collection_ids,
    summarize_collection_bundle_access_levels,
)


logger = logging.getLogger(__name__)

LANGUAGE_COUNT_CACHE_KEY = "explorer:language_count"
LANGUAGE_COUNT_CACHE_TIMEOUT = 86400  # 24 hours (invalidated on collection changes)
COLLECTION_PERMISSION_DENIED_MESSAGE = _(
    "This collection is restricted. If you believe you should have access, "
    "please contact lac-helpdesk@uni-koeln.de."
)


def _get_collection_by_pk_or_handle(queryset, pk=None, handle=None):
    if pk is not None:
        return queryset.filter(pk=pk).first()
    if handle is not None:
        collection = queryset.filter(identifier=handle).first()
        if collection is None and not handle.startswith("hdl:"):
            collection = queryset.filter(identifier=f"hdl:{handle}").first()
        return collection
    raise Http404("No collection identifier provided")


class CollectionLookupPermissionMixin(ACLPermissionMixin):
    permission_denied_message = COLLECTION_PERMISSION_DENIED_MESSAGE
    _resolved_collection = None

    def get_collection_queryset(self):
        raise NotImplementedError

    def get_collection(self, pk=None, handle=None):
        if self._resolved_collection is not None:
            return self._resolved_collection
        collection = _get_collection_by_pk_or_handle(
            self.get_collection_queryset(),
            pk=pk,
            handle=handle,
        )
        if collection is None:
            raise Http404("Collection not found")
        self._resolved_collection = collection
        return collection

    def get_acl_object(self, request, *args, **kwargs):
        return self.get_collection(
            pk=kwargs.get("pk"),
            handle=kwargs.get("handle"),
        )


class CollectionACLPermissionMixin(ACLPermissionMixin):
    permission_denied_message = COLLECTION_PERMISSION_DENIED_MESSAGE

    def dispatch(self, request, *args, **kwargs):
        acl_object = self.get_acl_object(request, *args, **kwargs)
        if acl_object is None:
            raise Http404("Collection not found")

        service = self.get_acl_service()
        result = service.evaluate(request.user, acl_object, mode=self.required_acl_mode)
        self.acl_result = result
        policy = self.get_exposure_policy_service()

        if self.allow_restricted_metadata and not policy.can_view_metadata(request.user, acl_object):
            return self.handle_no_permission(result)

        permissions = service._get_permissions(acl_object)
        has_explicit_acl_rules = bool(permissions and permissions.permissions_data)
        if (
            service.enforcement_enabled
            and has_explicit_acl_rules
            and not result.allowed
            and not self.allow_restricted_metadata
        ):
            return self.handle_no_permission(result)

        return super(ACLPermissionMixin, self).dispatch(request, *args, **kwargs)


class CollectionListView(ListView):
    model = Collection
    template_name = "collection_list.html"
    context_object_name = "collection_list"

    def get_paginate_by(self, queryset):
        return getattr(settings, "EXPLORER_COLLECTIONS_PAGE_SIZE", 25)

    def get_queryset(self):
        """Explicitly return all collections and log the count."""
        logger.info("Fetching collections in CollectionListView...")
        queryset = Collection.objects.prefetch_related(
            Prefetch(
                'general_info',
                queryset=CollectionGeneralInfo.objects.select_related('location').prefetch_related(
                    'keywords',
                    'object_languages',
                ),
                to_attr='prefetched_general_info',
            ),
            Prefetch(
                'publication_info',
                queryset=CollectionPublicationInfo.objects.prefetch_related('creators'),
                to_attr='prefetched_publication_info',
            ),
        ).annotate(
            bundles_count=Count('bundle_collection', distinct=True)
        ).filter(
            bundles_count__gt=0,
        )

        language_filter = self.request.GET.get("language", "").strip()
        if language_filter:
            queryset = queryset.filter(
                Q(general_info__object_languages__name__iexact=language_filter)
                | Q(general_info__object_languages__display_name__iexact=language_filter)
                | Q(general_info__object_languages__iso_639_3_code__iexact=language_filter)
            ).distinct()

        sort = self.request.GET.get('sort', 'name')
        order = self.request.GET.get('order', 'asc')
        prefix = '-' if order == 'desc' else ''

        if sort == 'language':
            queryset = queryset.annotate(first_language=Min('general_info__object_languages__name'))
            queryset = queryset.order_by(f'{prefix}first_language', 'general_info__display_title')
        elif sort == 'bundles':
            queryset = queryset.order_by(f'{prefix}bundles_count', 'general_info__display_title')
        else:
            queryset = queryset.order_by(f'{prefix}general_info__display_title')

        queryset = ExposurePolicyService().filter_collection_queryset(
            self.request.user,
            queryset,
            channel="browse",
        )
        return queryset

    def get_context_data(self, **kwargs):
        """Add processed location data to the context."""
        context = super().get_context_data(**kwargs)
        context["is_htmx"] = self.request.headers.get("HX-Request") == "true"
        context['current_sort'] = self.request.GET.get('sort', 'name')
        context['current_order'] = self.request.GET.get('order', 'asc')
        search_query = self.request.GET.get("q", "").strip()
        context["search_query"] = search_query
        language_filter = self.request.GET.get("language", "").strip()
        context["language_filter"] = language_filter
        if search_query:
            search_results = search_archives(search_query, user=self.request.user)
            context["search_results"] = search_results
            context["collection_search_results"] = [
                result for result in search_results if result.kind == "collection"
            ]
            context["bundle_search_results"] = [
                result for result in search_results if result.kind == "bundle"
            ]

        # Search results partial does not render the collection table/map.
        # Avoid loading and enriching the full collection queryset for this path.
        if context["is_htmx"] and search_query:
            return context

        collection_list = list(context['collection_list'])
        context['collection_list'] = collection_list
        collection_ids: list[str] = []
        for collection in collection_list:
            # Use prefetched data to avoid N+1 queries
            general_info_list = getattr(collection, 'prefetched_general_info', None)
            general_info = (
                general_info_list[0] if general_info_list else collection.get_general_info
            )
            collection.list_general_info = general_info
            collection.list_languages = (
                list(general_info.object_languages.all()) if general_info else []
            )
            collection.list_keywords = (
                list(general_info.keywords.all()) if general_info else []
            )
            collection.list_display_title = (
                general_info.display_title
                if general_info and general_info.display_title
                else (
                    general_info.title
                    if general_info and general_info.title
                    else collection.identifier
                )
            )
            collection.list_description = (
                general_info.description if general_info and general_info.description else ""
            )
            if general_info and general_info.location:
                location = general_info.location
                collection.formatted_location = get_formatted_location(location)
                collection.geo_location = location.geo_location
                collection.country_facet = location.country_facet
                collection.region_facet = location.region_facet
            else:
                collection.formatted_location = ""
                collection.geo_location = None
                collection.country_facet = None
                collection.region_facet = None

            publication_info_list = getattr(collection, 'prefetched_publication_info', None)
            publication_info = (
                publication_info_list[0] if publication_info_list else collection.get_publication_info
            )
            collection.list_publication_year = (
                publication_info.publication_year if publication_info else None
            )
            creators = list(publication_info.creators.all()) if publication_info else []
            collection.list_creators_display = ", ".join(
                " ".join(
                    part
                    for part in [creator.given_name, creator.family_name]
                    if part
                )
                for creator in creators
                if creator.given_name or creator.family_name
            )
            collection_ids.append(str(collection.pk))

        bundle_access_summaries = summarize_bundle_access_levels_by_collection_ids(collection_ids)
        for collection in collection_list:
            collection.bundle_access_summary = bundle_access_summaries.get(
                str(collection.pk),
                {"public": 0, "academic": 0, "restricted": 0, "total": 0},
            )

        is_table_sort_request = (
            context["is_htmx"]
            and self.request.headers.get('HX-Target') == 'collections-table'
        )

        context.setdefault('map_markers', [])
        if not context["is_htmx"] and not search_query:
            context['map_markers'] = json.loads(get_collection_map_markers())
            context['main_map_style_url'] = settings.EXPLORER_MAIN_MAP_STYLE_URL
            context['main_map_dark_style_url'] = settings.EXPLORER_MAIN_MAP_DARK_STYLE_URL

        all_filtered_collection_ids = collection_ids
        if context.get("is_paginated") and context.get("paginator"):
            all_filtered_collection_ids = [
                str(collection_id)
                for collection_id in context["paginator"].object_list.values_list("pk", flat=True)
            ]

        # Cache language count as it rarely changes.
        # For filtered subsets, derive the count from already prefetched languages.
        if language_filter:
            if context.get("is_paginated"):
                languages_count = (
                    CollectionObjectLanguage.objects.filter(
                        collectiongeneralinfo__collection_id__in=all_filtered_collection_ids
                    ).values('iso_639_3_code').distinct().count()
                )
            else:
                languages_count = len(
                    {
                        language.iso_639_3_code
                        for collection in collection_list
                        for language in collection.list_languages
                    }
                )
        else:
            languages_count = cache.get(LANGUAGE_COUNT_CACHE_KEY)
            if languages_count is None:
                languages_count = CollectionObjectLanguage.objects.filter(
                    collectiongeneralinfo__isnull=False
                ).values('iso_639_3_code').distinct().count()
                cache.set(LANGUAGE_COUNT_CACHE_KEY, languages_count, LANGUAGE_COUNT_CACHE_TIMEOUT)

        context['stats'] = {
            'collections_count': (
                context["paginator"].count if context.get("paginator") else len(collection_list)
            ),
            'languages_count': languages_count,
        }

        if is_table_sort_request:
            return context

        if not search_query:
            if context.get("is_paginated"):
                # For paginated lists, keep language index scoped to the full filtered set.
                iso_counts = dict(
                    CollectionObjectLanguage.objects.filter(
                        collectiongeneralinfo__collection_id__in=all_filtered_collection_ids
                    ).values('iso_639_3_code')
                    .annotate(cnt=Count('collectiongeneralinfo__collection', distinct=True))
                    .values_list('iso_639_3_code', 'cnt')
                )
                languages_list = list(
                    CollectionObjectLanguage.objects.filter(
                        collectiongeneralinfo__collection_id__in=all_filtered_collection_ids
                    )
                    .exclude(name__isnull=True)
                    .exclude(name__exact="")
                    .order_by('iso_639_3_code', '-pk')
                    .distinct('iso_639_3_code')
                )
                for language in languages_list:
                    language.collections_count = iso_counts.get(language.iso_639_3_code, 0)
            else:
                # Build language index from already prefetched row languages.
                iso_counts: dict[str | None, int] = {}
                representative_by_iso: dict[str | None, CollectionObjectLanguage] = {}

                for collection in collection_list:
                    seen_in_collection: set[str | None] = set()
                    for language in collection.list_languages:
                        iso_code = language.iso_639_3_code
                        if iso_code not in seen_in_collection:
                            iso_counts[iso_code] = iso_counts.get(iso_code, 0) + 1
                            seen_in_collection.add(iso_code)

                        existing = representative_by_iso.get(iso_code)
                        if existing is None or (language.pk or 0) > (existing.pk or 0):
                            representative_by_iso[iso_code] = language

                languages_list = [
                    language
                    for language in representative_by_iso.values()
                    if language.name
                ]
                for language in languages_list:
                    language.collections_count = iso_counts.get(language.iso_639_3_code, 0)

            language_spotlight = sorted(
                languages_list,
                key=lambda l: (-l.collections_count, l.name or ""),
            )
            language_index = sorted(languages_list, key=lambda l: (l.name or ""))
            for language in languages_list:
                entry = lookup_glottolog_entry(
                    glottocode=language.glottolog_code,
                    iso_code=language.iso_639_3_code,
                )
                if entry:
                    language.glottolog_macroarea = entry.get("macroarea")
                    language.glottolog_latitude = entry.get("latitude")
                    language.glottolog_longitude = entry.get("longitude")
            context['language_spotlight'] = language_spotlight
            context['language_index'] = language_index
            if language_filter:
                if context.get("is_paginated"):
                    selected = (
                        CollectionObjectLanguage.objects.filter(
                            collectiongeneralinfo__collection_id__in=all_filtered_collection_ids
                        )
                        .filter(
                            Q(name__iexact=language_filter)
                            | Q(display_name__iexact=language_filter)
                            | Q(iso_639_3_code__iexact=language_filter)
                        )
                        .order_by('iso_639_3_code', '-pk')
                        .distinct('iso_639_3_code')
                        .first()
                    )
                else:
                    normalized_filter = language_filter.lower()
                    matching_by_iso: dict[str | None, CollectionObjectLanguage] = {}
                    for collection in collection_list:
                        for language in collection.list_languages:
                            if not (
                                (language.name and language.name.lower() == normalized_filter)
                                or (
                                    language.display_name
                                    and language.display_name.lower() == normalized_filter
                                )
                                or (
                                    language.iso_639_3_code
                                    and language.iso_639_3_code.lower() == normalized_filter
                                )
                            ):
                                continue
                            iso_code = language.iso_639_3_code
                            existing = matching_by_iso.get(iso_code)
                            if existing is None or (language.pk or 0) > (existing.pk or 0):
                                matching_by_iso[iso_code] = language

                    selected = None
                    if matching_by_iso:
                        selected = sorted(
                            matching_by_iso.values(),
                            key=lambda language: (
                                language.iso_639_3_code is not None,
                                language.iso_639_3_code or "",
                            ),
                        )[0]
                if selected:
                    entry = lookup_glottolog_entry(
                        glottocode=selected.glottolog_code,
                        iso_code=selected.iso_639_3_code,
                    )
                    if entry:
                        selected.glottolog_macroarea = entry.get("macroarea")
                context['selected_language'] = selected

        return context

    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('HX-Request'):
            if 'q' in self.request.GET:
                return render(
                    self.request,
                    'explorer/partials/collection_search_results_content.html',
                    context,
                )
            if self.request.headers.get('HX-Target') == 'collection-language-shell':
                return render(
                    self.request,
                    'explorer/partials/collection_language_shell.html',
                    context,
                )
            if self.request.headers.get('HX-Target') == 'collections-table':
                return render(
                    self.request,
                    'explorer/partials/collections_table.html',
                    context,
                )
        return super().render_to_response(context, **response_kwargs)


class CollectionDetailView(MetadataExposureMixin, HandleLookupMixin, CollectionACLPermissionMixin, DetailView):
    """Detail view for a collection, accessible by UUID or handle."""

    model = Collection
    template_name = "collection_detail.html"
    context_object_name = "collection"
    permission_denied_message = COLLECTION_PERMISSION_DENIED_MESSAGE
    def get_queryset(self):
        return Collection.objects.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "general_info__keywords",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "structural_info",
            "structural_info__additional_metadata_files",
            "administrative_info",
            "administrative_info__licenses",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.object.get_general_info and self.object.get_general_info.location:
            location = self.object.get_general_info.location
            self.object.formatted_location = get_formatted_location(location)
            self.object.geo_location = location.geo_location
            self.object.region_facet = location.region_facet
            self.object.country_facet = location.country_facet
        else:
            self.object.formatted_location = ""
            self.object.geo_location = None
            self.object.region_facet = None
            self.object.country_facet = None

        page_number = self.request.GET.get('bundle_page')
        bundle_search = self.request.GET.get('bundle_search', '').strip()
        bundle_sort = self.request.GET.get('bundle_sort', 'name')
        bundle_order = self.request.GET.get('bundle_order', 'asc')
        allowed_per_page = {10, 25, 50}
        try:
            bundle_per_page = int(self.request.GET.get('bundle_per_page', 10))
        except (ValueError, TypeError):
            bundle_per_page = 10
        if bundle_per_page not in allowed_per_page:
            bundle_per_page = 10
        if bundle_sort not in {"name", "access"}:
            bundle_sort = "name"
        if bundle_order not in {"asc", "desc"}:
            bundle_order = "asc"
        context['bundle_search'] = bundle_search
        context['bundle_current_sort'] = bundle_sort
        context['bundle_current_order'] = bundle_order
        context['bundle_per_page'] = bundle_per_page
        page_obj, bundle_contexts = paginate_bundle_contexts(
            self.object,
            page_number,
            per_page=bundle_per_page,
            search_query=bundle_search or None,
            sort=bundle_sort,
            order=bundle_order,
        )

        query_params = self.request.GET.copy()
        for key in ('bundle_page', 'bundle_per_page'):
            if key in query_params:
                query_params.pop(key)
        base_query = query_params.urlencode()
        if base_query:
            base_url = f"{self.request.path}?{base_query}"
        else:
            base_url = self.request.path
        separator = '&' if '?' in base_url else '?'

        sort_query_params = self.request.GET.copy()
        for key in ('bundle_page', 'bundle_per_page', 'bundle_sort', 'bundle_order'):
            if key in sort_query_params:
                sort_query_params.pop(key)
        sort_base_query = sort_query_params.urlencode()
        if sort_base_query:
            sort_base_url = f"{self.request.path}?{sort_base_query}"
        else:
            sort_base_url = self.request.path
        sort_separator = '&' if '?' in sort_base_url else '?'

        context['bundle_page_obj'] = page_obj
        context['bundle_contexts'] = bundle_contexts
        context['bundle_page_base_url'] = base_url
        context['bundle_page_separator'] = separator
        context['bundle_sort_base_url'] = sort_base_url
        context['bundle_sort_separator'] = sort_separator
        context['bundles_total'] = page_obj.paginator.count if page_obj else 0
        context['bundle_access_summary'] = summarize_collection_bundle_access_levels(self.object)

        acl_service = ACLEvaluationService()
        bundle_ids = [
            str(bundle_info["bundle"].pk)
            for bundle_info in bundle_contexts
            if bundle_info.get("bundle")
        ]
        bundle_permissions_by_id: dict[str, ACLPermissions] = {}

        bundle_content_type = ContentType.objects.get_for_model(Bundle)
        collection_content_type = ContentType.objects.get_for_model(Collection)

        if bundle_ids:
            for permission in ACLPermissions.objects.filter(
                content_type=bundle_content_type,
                object_id__in=bundle_ids,
            ).order_by("id"):
                bundle_permissions_by_id.setdefault(str(permission.object_id), permission)

        collection_permission = (
            ACLPermissions.objects.filter(
                content_type=collection_content_type,
                object_id=str(self.object.pk),
            )
            .order_by("id")
            .first()
        )
        self.object._acl_permissions = collection_permission

        for bundle_info in bundle_contexts:
            bundle = bundle_info.get("bundle")
            if not bundle:
                continue
            bundle._acl_parent = self.object
            bundle._acl_permissions = bundle_permissions_by_id.get(str(bundle.pk))

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

        # Display only administrative content licenses in the collection header.
        context["content_licenses"] = []

        if hasattr(self.object, "administrative_info") and self.object.administrative_info.first():
            context["content_licenses"] = self.object.administrative_info.first().licenses.all()

        # Citation
        context['citation'] = self._format_citation()

        return context

    def _format_citation(self) -> str:
        """
        Format citation for the collection.

        Format: Creator1 family, given, Creator2 given family & Creator3 given family.
                Year. Title. Language Archive Cologne. Handle URL.
        """
        parts = []

        # Get creators from publication info
        pub_info = self.object.publication_info.first()
        if pub_info:
            creators = list(pub_info.creators.all())

            if creators:
                creator_names = []
                for i, creator in enumerate(creators):
                    if i == 0:
                        # First creator: "family, given"
                        if creator.given_name:
                            creator_names.append(f"{creator.family_name}, {creator.given_name}")
                        else:
                            creator_names.append(creator.family_name)
                    else:
                        # Other creators: "given family"
                        if creator.given_name:
                            creator_names.append(f"{creator.given_name} {creator.family_name}")
                        else:
                            creator_names.append(creator.family_name)

                # Join with ", " and " & " before the last one
                if len(creator_names) == 1:
                    parts.append(creator_names[0])
                elif len(creator_names) == 2:
                    parts.append(f"{creator_names[0]} & {creator_names[1]}")
                else:
                    parts.append(", ".join(creator_names[:-1]) + " & " + creator_names[-1])

            # Publication year
            if pub_info.publication_year:
                parts.append(str(pub_info.publication_year))

        # Title (from general info)
        general_info = self.object.get_general_info
        if general_info and general_info.display_title:
            parts.append(general_info.display_title)

        # Data provider
        parts.append("Language Archive Cologne")

        # Handle URL
        if self.object.identifier:
            handle = self.object.identifier
            if handle.startswith('hdl:'):
                handle_url = f"https://hdl.handle.net/{handle[4:]}"
            else:
                handle_url = handle
            parts.append(handle_url)

        return ". ".join(parts) + "." if parts else ""

    def render_to_response(self, context, **response_kwargs):
        # CLARIN content negotiation: return CMDI/XML if requested
        accept = self.request.headers.get('Accept', '')
        if 'application/x-cmdi+xml' in accept:
            return redirect('explorer:collection_xml_by_handle', handle=self.object.handle_path)

        if self.request.headers.get('HX-Request'):
            if (
                'bundle_page' in self.request.GET
                or 'bundle_per_page' in self.request.GET
                or 'bundle_search' in self.request.GET
                or 'bundle_sort' in self.request.GET
                or 'bundle_order' in self.request.GET
            ):
                context['bundles_header_oob'] = True
                return render(
                    self.request,
                    'explorer/partials/collection_bundles_table.html',
                    context,
                )
        return super().render_to_response(context, **response_kwargs)


class CollectionResourcesView(View):
    """View for accessing collection additional metadata files.

    Additional metadata files are always public and do not require ACL checks.
    """

    def get(self, request, pk=None, handle=None, resource_id=None):
        collection = get_object_by_pk_or_handle(Collection, pk=pk, handle=handle)
        policy = ExposurePolicyService()

        if not resource_id:
            raise Http404("Resource ID required")

        action = request.GET.get('action', 'view')

        try:
            decoded_resource_id = unquote(resource_id)
            if decoded_resource_id.startswith('ID_'):
                decoded_resource_id = decoded_resource_id[3:]

            # URLs no longer include hdl: prefix, but DB stores it
            if not decoded_resource_id.startswith('hdl:'):
                decoded_resource_id = f"hdl:{decoded_resource_id}"

            # Try to find the metadata file in the collection's additional metadata
            metadata_file = None
            structural_info = collection.structural_info.first()
            if structural_info:
                metadata_file = structural_info.additional_metadata_files.filter(
                    file_pid=decoded_resource_id
                ).first()

            if metadata_file is not None:
                denied_response = enforce_binary_exposure(
                    request,
                    metadata_file,
                    denial_message=COLLECTION_PERMISSION_DENIED_MESSAGE,
                    policy=policy,
                )
                if denied_response is not None:
                    return denied_response

            if metadata_file is None:
                raise Http404(f"Collection metadata resource {decoded_resource_id} not found")

            resource_service = ResourceMappingService(skip_bucket_check=True)
            storage_resolution = resolve_collection_metadata_to_presigned(
                resource_service,
                metadata_file,
                collection,
            )
            if not storage_resolution:
                raise ValueError(f"No S3 location found for PID: {decoded_resource_id}")

            # Get file information for display
            file_name = metadata_file.file_name if metadata_file else storage_resolution["key"].split('/')[-1]
            file_description = metadata_file.file_description if metadata_file else ''
            mime_type = metadata_file.mime_type if metadata_file else 'application/octet-stream'

            detected_media_type = determine_media_type(mime_type, file_name)
            source_mime_type = guess_source_mime_type(mime_type, file_name, detected_media_type)
            subtitle_url = None
            if detected_media_type == 'video' and structural_info:
                subtitle_url = find_subtitle_for_collection_video(
                    collection,
                    structural_info,
                    metadata_file,
                    resource_service,
                )

            # Generate presigned URL for streaming/preview
            presigned_url = storage_resolution["url"]

            # Generate download URL with proper content disposition
            download_headers = {
                'ResponseContentDisposition': build_content_disposition(file_name),
            }
            if source_mime_type:
                download_headers['ResponseContentType'] = source_mime_type

            download_url = resource_service.generate_presigned_url(
                storage_resolution["bucket"],
                storage_resolution["key"],
                response_headers=download_headers,
            )

            is_htmx = request.headers.get('HX-Request') == 'true'
            if is_htmx and action in {'play', 'view'} and is_imdi_resource(file_name, mime_type):
                imdi_modal_response = render_imdi_modal_response(
                    request,
                    s3_client=getattr(resource_service, "s3_client", None),
                    bucket=storage_resolution["bucket"],
                    key=storage_resolution["key"],
                    collection=collection,
                )
                if imdi_modal_response is not None:
                    return imdi_modal_response

            xml_preview = None
            if is_htmx and action in {'play', 'view'} and detected_media_type == 'xml':
                xml_preview = load_xml_preview(
                    resource_service,
                    storage_resolution["bucket"],
                    storage_resolution["key"],
                )

            markdown_html = None
            if is_htmx and action in {'play', 'view'} and detected_media_type == 'markdown':
                markdown_html = load_markdown_preview(
                    resource_service,
                    storage_resolution["bucket"],
                    storage_resolution["key"],
                )

            if action == 'download':
                raise Http404("Direct downloads are not available")

            peaks_url = None
            spectrogram_data_url = None
            spectrogram_available = False
            pitch_data_url = None
            pitch_available = False
            if detected_media_type == 'audio':
                peaks_url = self._resolve_peaks_url(
                    resource_service,
                    storage_resolution["bucket"],
                    storage_resolution["key"],
                )
                spectrogram_available = self._spectrogram_data_exists(
                    resource_service,
                    storage_resolution["bucket"],
                    storage_resolution["key"],
                )
                if action == 'analyze':
                    if spectrogram_available:
                        spectrogram_data_url = resource_service.generate_presigned_url(
                            storage_resolution["bucket"],
                            MediaProcessingService._derivative_s3_key(storage_resolution["key"], ".spectrogram.bin"),
                        )
                pitch_available = self._pitch_data_exists(
                    resource_service,
                    storage_resolution["bucket"],
                    storage_resolution["key"],
                )
                if action == 'pitch' and pitch_available:
                    pitch_data_url = resource_service.generate_presigned_url(
                        storage_resolution["bucket"],
                        MediaProcessingService._derivative_s3_key(storage_resolution["key"], ".pitch.bin"),
                    )

            player_mode = 'simple'
            if detected_media_type == 'audio':
                if action == 'pitch' and pitch_data_url:
                    player_mode = 'pitch'
                elif action == 'analyze' and bool(spectrogram_data_url):
                    player_mode = 'analyze'

            resource_play_url = f"{request.path}?action=play"
            resource_analyze_url = f"{request.path}?action=analyze"
            resource_pitch_url = f"{request.path}?action=pitch"

            if is_htmx and action in {'play', 'view', 'analyze', 'pitch'}:
                return self._render_htmx_modal(
                    request, file_name, file_description, mime_type,
                    detected_media_type, source_mime_type, presigned_url, download_url,
                    xml_preview=xml_preview,
                    markdown_html=markdown_html,
                    download_bucket=storage_resolution["bucket"],
                    download_key=storage_resolution["key"],
                    peaks_url=peaks_url,
                    spectrogram_data_url=spectrogram_data_url,
                    player_mode=player_mode,
                    spectrogram_available=spectrogram_available,
                    pitch_data_url=pitch_data_url,
                    pitch_available=pitch_available,
                    subtitle_url=subtitle_url,
                    resource_play_url=resource_play_url,
                    resource_analyze_url=resource_analyze_url,
                    resource_pitch_url=resource_pitch_url,
                )

            if action in {'play', 'view', 'analyze', 'pitch'}:
                return redirect(
                    'explorer:collection_detail_by_handle',
                    handle=collection.identifier,
                )

            raise Http404("Unsupported action")

        except ValueError as e:
            logger.error("Resource mapping service error", extra={"error": str(e)})
            raise Http404(f"Resource {resource_id} not found or cannot be accessed")
        except Exception as e:
            logger.error("Error accessing resource", extra={"error": str(e)})
            raise Http404(f"Error accessing resource: {str(e)}")

    def _render_htmx_modal(
        self, request, file_name, file_description, mime_type,
        detected_media_type, source_mime_type, presigned_url, download_url,
        xml_preview=None,
        markdown_html=None,
        download_bucket=None,
        download_key=None,
        peaks_url=None,
        spectrogram_data_url=None,
        player_mode='simple',
        spectrogram_available=False,
        pitch_data_url=None,
        pitch_available=False,
        subtitle_url=None,
        resource_play_url=None,
        resource_analyze_url=None,
        resource_pitch_url=None,
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
            'download_bucket': download_bucket,
            'download_key': download_key,
            'download_filename': file_name,
            'elan_context': None,
            'xml_content': xml_preview,
            'markdown_html': markdown_html,
            'peaks_url': peaks_url,
            'spectrogram_data_url': spectrogram_data_url,
            'player_mode': player_mode,
            'spectrogram_available': spectrogram_available,
            'pitch_data_url': pitch_data_url,
            'pitch_available': pitch_available,
            'subtitle_url': subtitle_url,
            'resource_play_url': resource_play_url,
            'resource_analyze_url': resource_analyze_url,
            'resource_pitch_url': resource_pitch_url,
        }

        response = render(
            request,
            'explorer/partials/resource_modal_content.html',
            modal_context,
        )
        response['HX-Trigger'] = json.dumps({'showResourceModal': True})
        return response

    def _resolve_peaks_url(self, resource_service, bucket_name, object_key):
        """Check if pre-computed peaks exist and return a presigned URL."""
        peaks_key = MediaProcessingService._derivative_s3_key(object_key, ".peaks.json")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=peaks_key)
            return resource_service.generate_presigned_url(bucket_name, peaks_key)
        except Exception:
            return None

    def _resolve_spectrogram_data_url(self, resource_service, bucket_name, object_key):
        """Check if pre-computed spectrogram frequencies exist and return a presigned URL."""
        spectrogram_data_key = MediaProcessingService._derivative_s3_key(object_key, ".spectrogram.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=spectrogram_data_key)
            return resource_service.generate_presigned_url(bucket_name, spectrogram_data_key)
        except Exception:
            return None

    def _spectrogram_data_exists(self, resource_service, bucket_name, object_key):
        """Check if pre-computed spectrogram sidecar exists."""
        spectrogram_data_key = MediaProcessingService._derivative_s3_key(object_key, ".spectrogram.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=spectrogram_data_key)
            return True
        except Exception:
            return False

    def _pitch_data_exists(self, resource_service, bucket_name, object_key):
        """Check if pre-computed pitch sidecar exists."""
        pitch_key = MediaProcessingService._derivative_s3_key(object_key, ".pitch.bin")
        try:
            resource_service.s3_client.head_object(Bucket=bucket_name, Key=pitch_key)
            return True
        except Exception:
            return False


class CollectionJsonLdView(MetadataExposureMixin, CollectionLookupPermissionMixin, CollectionACLPermissionMixin, View):
    """Export collection metadata as JSON-LD."""

    def get_collection_queryset(self):
        return Collection.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__taxonomy",
            "general_info__object_languages__taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__additional_metadata_files",
            "project_infos",
            "project_infos__funder_infos",
            "project_infos__funder_infos__funder_identifiers",
            "bundle_collection",
            "bundle_collection__bundle",
            "bundle_collection__bundle__general_info",
        )

    def get(self, request, pk=None, handle=None):
        collection = self.get_collection(pk=pk, handle=handle)

        serializer = CollectionJsonLdSerializer(collection)
        data = serializer.serialize()

        if request.headers.get("HX-Request") == "true":
            from django.core.serializers.json import DjangoJSONEncoder
            content = json.dumps(data, indent=2, ensure_ascii=False, cls=DjangoJSONEncoder)
            return render(request, "explorer/partials/metadata_preview.html", {
                "content": content,
                "language_class": "language-json",
            })

        response = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
        response["Content-Type"] = "application/ld+json"

        general_info = collection.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(collection.id)[:8]
        response["Content-Disposition"] = f'attachment; filename="{filename}.jsonld"'

        return response


class CollectionXmlView(MetadataExposureMixin, CollectionLookupPermissionMixin, CollectionACLPermissionMixin, View):
    """Export collection metadata as BLAM XML."""

    def get_collection_queryset(self):
        return Collection.objects.prefetch_related(
            "header",
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__object_languages__alternative_names",
            "general_info__object_languages__taxonomy",
            "general_info__object_languages__taxonomy__language_family",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
            "administrative_info",
            "administrative_info__licenses",
            "administrative_info__rights_holders",
            "administrative_info__rights_holders__rights_holder_identifiers",
            "administrative_info__is_identical_to",
            "structural_info",
            "structural_info__additional_metadata_files",
            "project_infos",
            "project_infos__funder_infos",
            "project_infos__funder_infos__funder_identifiers",
        )

    def get(self, request, pk=None, handle=None):
        collection = self.get_collection(pk=pk, handle=handle)

        exporter = CollectionExporter()
        try:
            xml_content = exporter.export(collection)
        except Exception as e:
            logger.exception("Failed to export collection %s as XML", collection.identifier)
            msg = f"Error generating XML for collection {collection.identifier}: {e}"
            if request.headers.get("HX-Request") == "true":
                return render(request, "explorer/partials/metadata_preview.html", {
                    "content": msg,
                    "language_class": "language-plain",
                })
            return HttpResponse(msg, content_type="text/plain", status=500)

        if request.headers.get("HX-Request") == "true":
            return render(request, "explorer/partials/metadata_preview.html", {
                "content": xml_content,
                "language_class": "language-xml",
            })

        general_info = collection.general_info.first()
        if general_info and general_info.display_title:
            filename = general_info.display_title.replace(" ", "_")[:50]
        else:
            filename = str(collection.id)[:8]

        response = HttpResponse(xml_content, content_type="application/xml")
        response["Content-Disposition"] = f'attachment; filename="{filename}.xml"'
        return response
