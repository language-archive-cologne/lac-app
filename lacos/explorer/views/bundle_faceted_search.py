"""Faceted search view for bundle discovery."""

from django.db.models import Min
from django.shortcuts import render
from django.views.generic import ListView

from lacos.blam.models import Bundle
from lacos.explorer.advanced_search import BUNDLE_FIELD_DEFINITIONS
from lacos.explorer.advanced_search import apply_field_scoped_search
from lacos.explorer.facet_querysets import bundle_facet_queryset
from lacos.explorer.facets import BUNDLE_FACET_CACHE_KEY
from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.facets import FacetedSearchResult
from lacos.explorer.facets import FacetService
from lacos.explorer.match_reasons import attach_bundle_match_reasons
from lacos.explorer.search_access_views import SearchAccessRequiredMixin
from lacos.explorer.search_safeguards import CountlessPaginationMixin
from lacos.explorer.search_safeguards import SearchRequestBudgetMixin
from lacos.explorer.search_shell import SearchShellMixin
from lacos.explorer.text_search import apply_text_search

BUNDLE_SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "collection": "collection_identifier",
}


class BundleFacetedSearchView(
    SearchAccessRequiredMixin,
    SearchShellMixin,
    SearchRequestBudgetMixin,
    CountlessPaginationMixin,
    ListView,
):
    model = Bundle
    template_name = "bundle_faceted_search.html"
    context_object_name = "bundles"
    paginate_by = 25
    _faceted_result: FacetedSearchResult | None = None
    _search_in: list[str] = []
    search_shell_facet_cache_key = BUNDLE_FACET_CACHE_KEY
    search_shell_field_definitions = BUNDLE_FIELD_DEFINITIONS

    def get_queryset(self):
        base_qs = bundle_facet_queryset()

        search_query = self.request.GET.get("q", "").strip()
        valid_keys = {d.key for d in BUNDLE_FIELD_DEFINITIONS}
        self._search_in = [
            k for k in self.request.GET.getlist("search_in") if k in valid_keys
        ]
        if search_query:
            if self._search_in:
                base_qs = apply_field_scoped_search(
                    base_qs, search_query, self._search_in, BUNDLE_FIELD_DEFINITIONS
                )
            else:
                base_qs = apply_text_search(base_qs, search_query)

        facet_cache_key = BUNDLE_FACET_CACHE_KEY if not search_query else None
        self._faceted_result = FacetService(
            definitions=BUNDLE_FACET_DEFINITIONS
        ).search(
            self.request.GET,
            base_qs,
            cache_key=facet_cache_key,
            cross_filter_counts=False,
        )
        qs = self._faceted_result.queryset

        sort_key = self.request.GET.get("sort", "name")
        order = self.request.GET.get("order", "asc")

        # Only add expensive Min() annotations when actually sorting by them
        if sort_key == "language":
            qs = qs.annotate(
                first_language=Min("general_info__object_languages__name"),
            )
        elif sort_key == "collection":
            qs = qs.annotate(
                collection_identifier=Min(
                    "structural_info__is_member_of_collection__identifier"
                ),
            )

        sort_field = BUNDLE_SORT_ALLOWLIST.get(
            sort_key, "general_info__display_title"
        )
        prefix = "-" if order == "desc" else ""
        qs = qs.order_by(
            f"{prefix}{sort_field}",
            "general_info__display_title",
            "pk",
        )

        qs = qs.prefetch_related(
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__location",
            "structural_info",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors__contributor_name",
        )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self._faceted_result:
            context["facets"] = self._faceted_result.facets
            context["active_filters"] = self._faceted_result.active_filters
            context["has_active_filters"] = bool(self._faceted_result.active_filters)
        page = context.get("page_obj")
        context["total_count"] = page.known_count if page else 0
        context["total_count_is_lower_bound"] = bool(page and page.has_next())
        context["search_query"] = self.request.GET.get("q", "")
        context["current_sort"] = self.request.GET.get("sort", "name")
        context["current_order"] = self.request.GET.get("order", "asc")
        context["current_params"] = self.request.GET.copy()
        context["field_definitions"] = BUNDLE_FIELD_DEFINITIONS
        context["active_search_in"] = self._search_in
        if context["search_query"]:
            attach_bundle_match_reasons(
                context.get("bundles", ()),
                context["search_query"],
            )
        return context

    def render_to_response(self, context, **kwargs):
        if self.request.headers.get("HX-Request"):
            response = render(
                self.request,
                "explorer/partials/bundle_faceted_results.html",
                context,
            )
        else:
            response = super().render_to_response(context, **kwargs)
        if self._faceted_result:
            response.headers["Server-Timing"] = self._faceted_result.server_timing
        return response
