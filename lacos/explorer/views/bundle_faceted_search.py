"""Faceted search view for bundle discovery."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, Min, OuterRef, Subquery
from django.db.models.functions import Cast
from django.shortcuts import render
from django.views.generic import ListView

from lacos.blam.models import Bundle
from lacos.explorer.facets import (
    BUNDLE_FACET_CACHE_KEY,
    BUNDLE_FACET_DEFINITIONS,
    FacetedSearchResult,
    FacetService,
)
from lacos.explorer.text_search import apply_text_search
from lacos.storage.models.acl_permissions import ACLPermissions

BUNDLE_SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "collection": "collection_identifier",
}


class BundleFacetedSearchView(ListView):
    model = Bundle
    template_name = "bundle_faceted_search.html"
    context_object_name = "bundles"
    paginate_by = 50
    _faceted_result: FacetedSearchResult | None = None

    def get_queryset(self):
        bundle_ct = ContentType.objects.get_for_model(Bundle)
        base_qs = Bundle.objects.annotate(
            acl_access_level=Subquery(
                ACLPermissions.objects.filter(
                    content_type=bundle_ct,
                    object_id=Cast(OuterRef("pk"), output_field=CharField()),
                ).values("access_level")[:1]
            )
        )

        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            base_qs = apply_text_search(base_qs, search_query)

        facet_cache_key = BUNDLE_FACET_CACHE_KEY if not search_query else None
        self._faceted_result = FacetService(
            definitions=BUNDLE_FACET_DEFINITIONS
        ).search(self.request.GET, base_qs, cache_key=facet_cache_key)
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
        qs = qs.order_by(f"{prefix}{sort_field}", "general_info__display_title")

        qs = qs.prefetch_related(
            "general_info",
            "general_info__object_languages",
            "general_info__location",
            "structural_info",
            "structural_info__bundle_topics",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
            "publication_info",
        )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self._faceted_result:
            context["facets"] = self._faceted_result.facets
            context["active_filters"] = self._faceted_result.active_filters
            context["has_active_filters"] = bool(self._faceted_result.active_filters)
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
                self.request,
                "explorer/partials/bundle_faceted_results.html",
                context,
            )
        return super().render_to_response(context, **kwargs)
