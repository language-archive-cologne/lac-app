"""Faceted search view for collection discovery."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, Count, Min, OuterRef, Subquery
from django.db.models.functions import Cast
from django.shortcuts import render
from django.views.generic import ListView

from lacos.blam.models import Collection
from lacos.explorer.facets import FACET_CACHE_KEY, FacetService, FacetedSearchResult
from lacos.explorer.text_search import apply_text_search
from lacos.storage.models.acl_permissions import ACLPermissions

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
        collection_ct = ContentType.objects.get_for_model(Collection)
        base_qs = Collection.objects.annotate(
            acl_access_level=Subquery(
                ACLPermissions.objects.filter(
                    content_type=collection_ct,
                    object_id=Cast(OuterRef("pk"), output_field=CharField()),
                ).values("access_level")[:1]
            )
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            base_qs = apply_text_search(base_qs, search_query)

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
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__location",
            "publication_info",
            "publication_info__creators",
        )

        return qs

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
