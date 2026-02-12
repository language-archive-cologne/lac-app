"""Faceted search view for collection discovery."""

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.models import Count, Min
from django.shortcuts import render
from django.views.generic import ListView

from lacos.blam.models import Collection
from lacos.explorer.facets import FACET_CACHE_KEY, FacetService, FacetedSearchResult

SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "bundles": "bundles_count",
}


class FacetedSearchView(ListView):
    model = Collection
    template_name = "faceted_search.html"
    context_object_name = "collections"
    paginate_by = 50
    _faceted_result: FacetedSearchResult | None = None

    def get_queryset(self):
        # Clean base queryset for facet counting — no extra JOINs that inflate counts.
        # Annotations like bundles_count/first_language are added AFTER filtering.
        base_qs = Collection.objects.all()

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            base_qs = self._apply_text_search(base_qs, search_query)

        # Cache facet counts when there is no text search (base case).
        facet_cache_key = FACET_CACHE_KEY if not search_query else None
        self._faceted_result = FacetService().search(
            self.request.GET, base_qs, cache_key=facet_cache_key
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
        qs = qs.order_by(f"{prefix}{sort_field}", "general_info__display_title")

        qs = qs.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
        )

        return qs

    def _apply_text_search(self, qs, search_term):
        """Apply full-text search using a subquery to avoid duplicate rows.

        SearchVector joins across M2M tables (keywords, languages) which
        multiplies rows.  Using a subquery keeps the outer queryset clean.
        """
        prefix_terms = " & ".join(f"{word}:*" for word in search_term.split())
        query = SearchQuery(prefix_terms, config="simple", search_type="raw")

        matching_pks = (
            Collection.objects.annotate(
                computed_search_vector=(
                    SearchVector("identifier", weight="A", config="simple")
                    + SearchVector("general_info__display_title", weight="A", config="simple")
                    + SearchVector("general_info__description", weight="B", config="simple")
                    + SearchVector("general_info__keywords__value", weight="B", config="simple")
                    + SearchVector("general_info__object_languages__name", weight="C", config="simple")
                    + SearchVector("general_info__location__country_facet", weight="D", config="simple")
                ),
            )
            .filter(computed_search_vector=query)
            .values("pk")
        )

        return qs.filter(pk__in=matching_pks)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self._faceted_result:
            context["facets"] = self._faceted_result.facets
            context["active_filters"] = self._faceted_result.active_filters
            context["has_active_filters"] = bool(self._faceted_result.active_filters)
        # Reuse paginator's count to avoid a duplicate COUNT query.
        paginator = context.get("paginator")
        context["total_count"] = paginator.count if paginator else 0
        context["search_query"] = self.request.GET.get("q", "")
        context["current_sort"] = self.request.GET.get("sort", "name")
        context["current_order"] = self.request.GET.get("order", "asc")
        context["current_params"] = self.request.GET.copy()
        return context

    def render_to_response(self, context, **kwargs):
        if self.request.headers.get("HX-Request"):
            return render(
                self.request, "explorer/partials/faceted_results.html", context
            )
        return super().render_to_response(context, **kwargs)
