"""Faceted search view for collection discovery."""

from django.db.models import Count, Min
from django.shortcuts import render
from django.views.generic import ListView

from lacos.blam.models import Collection
from lacos.explorer.advanced_search import (
    COLLECTION_FIELD_DEFINITIONS,
    apply_field_scoped_search,
)
from lacos.explorer.facet_querysets import collection_facet_queryset
from lacos.explorer.facets import FACET_CACHE_KEY, FacetedSearchResult, FacetService
from lacos.explorer.search_safeguards import (
    CountlessPaginationMixin,
    SearchRequestBudgetMixin,
)
from lacos.explorer.text_search import apply_text_search

SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "bundles": "bundles_count",
}


class FacetedSearchView(SearchRequestBudgetMixin, CountlessPaginationMixin, ListView):
    model = Collection
    template_name = "faceted_search.html"
    context_object_name = "collections"
    paginate_by = 25
    _faceted_result: FacetedSearchResult | None = None
    _search_in: list[str] = []

    def get_queryset(self):
        # Clean base queryset for facet counting — no extra JOINs that inflate counts.
        # Annotations like bundles_count/first_language are added AFTER filtering.
        base_qs = collection_facet_queryset()

        search_query = self.request.GET.get("q", "").strip()
        valid_keys = {d.key for d in COLLECTION_FIELD_DEFINITIONS}
        self._search_in = [
            k for k in self.request.GET.getlist("search_in") if k in valid_keys
        ]
        if search_query:
            if self._search_in:
                base_qs = apply_field_scoped_search(
                    base_qs, search_query, self._search_in, COLLECTION_FIELD_DEFINITIONS
                )
            else:
                base_qs = apply_text_search(base_qs, search_query)

        # Cache facet counts when there is no text search (base case).
        facet_cache_key = FACET_CACHE_KEY if not search_query else None
        self._faceted_result = FacetService().search(
            self.request.GET,
            base_qs,
            cache_key=facet_cache_key,
            cross_filter_counts=False,
        )
        qs = self._faceted_result.queryset

        # bundles_count is always needed for display in the table
        qs = qs.annotate(
            bundles_count=Count("bundle_collection", distinct=True),
        )

        sort_key = self.request.GET.get("sort", "name")
        order = self.request.GET.get("order", "asc")

        # Only add expensive Min() annotation when sorting by language
        if sort_key == "language":
            qs = qs.annotate(
                first_language=Min("general_info__object_languages__name"),
            )

        sort_field = SORT_ALLOWLIST.get(sort_key, "general_info__display_title")
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
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors",
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
        context["field_definitions"] = COLLECTION_FIELD_DEFINITIONS
        context["active_search_in"] = self._search_in
        return context

    def render_to_response(self, context, **kwargs):
        if self.request.headers.get("HX-Request"):
            response = render(
                self.request, "explorer/partials/faceted_results.html", context
            )
        else:
            response = super().render_to_response(context, **kwargs)
        if self._faceted_result:
            response.headers["Server-Timing"] = self._faceted_result.server_timing
        return response
