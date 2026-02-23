"""Field-based search views with dynamic query builder."""

from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, Count, Min, OuterRef, Subquery
from django.db.models.functions import Cast
from django.views.generic import ListView

from lacos.blam.models import Bundle, Collection
from lacos.explorer.advanced_search import (
    BUNDLE_FIELD_DEFINITIONS,
    COLLECTION_FIELD_DEFINITIONS,
    apply_search_rows,
    parse_search_rows,
)
from lacos.storage.models.acl_permissions import ACLPermissions

COLLECTION_SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "bundles": "bundles_count",
}

BUNDLE_SORT_ALLOWLIST = {
    "name": "general_info__display_title",
    "language": "first_language",
    "collection": "collection_identifier",
}


class FieldSearchView(ListView):
    """Collection search using dynamic per-field query builder."""

    model = Collection
    template_name = "field_search.html"
    context_object_name = "collections"
    paginate_by = 50

    def get_queryset(self):
        collection_ct = ContentType.objects.get_for_model(Collection)
        qs = Collection.objects.annotate(
            acl_access_level=Subquery(
                ACLPermissions.objects.filter(
                    content_type=collection_ct,
                    object_id=Cast(OuterRef("pk"), output_field=CharField()),
                ).values("access_level")[:1]
            )
        )

        rows = parse_search_rows(self.request.GET, COLLECTION_FIELD_DEFINITIONS)
        qs = apply_search_rows(qs, rows, COLLECTION_FIELD_DEFINITIONS)

        qs = qs.annotate(
            bundles_count=Count("bundle_collection", distinct=True),
        )

        sort_key = self.request.GET.get("sort", "name")
        order = self.request.GET.get("order", "asc")

        if sort_key == "language":
            qs = qs.annotate(
                first_language=Min("general_info__object_languages__name"),
            )

        sort_field = COLLECTION_SORT_ALLOWLIST.get(sort_key, "general_info__display_title")
        prefix = "-" if order == "desc" else ""
        qs = qs.order_by(f"{prefix}{sort_field}", "general_info__display_title")

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
        paginator = context.get("paginator")
        context["total_count"] = paginator.count if paginator else 0
        context["current_sort"] = self.request.GET.get("sort", "name")
        context["current_order"] = self.request.GET.get("order", "asc")
        context["current_params"] = self.request.GET.copy()

        rows = parse_search_rows(self.request.GET, COLLECTION_FIELD_DEFINITIONS)
        context["search_rows"] = rows
        context["has_search_rows"] = bool(rows)
        context["field_definitions"] = COLLECTION_FIELD_DEFINITIONS
        return context


class BundleFieldSearchView(ListView):
    """Bundle search using dynamic per-field query builder."""

    model = Bundle
    template_name = "bundle_field_search.html"
    context_object_name = "bundles"
    paginate_by = 50

    def get_queryset(self):
        bundle_ct = ContentType.objects.get_for_model(Bundle)
        qs = Bundle.objects.annotate(
            acl_access_level=Subquery(
                ACLPermissions.objects.filter(
                    content_type=bundle_ct,
                    object_id=Cast(OuterRef("pk"), output_field=CharField()),
                ).values("access_level")[:1]
            )
        )

        rows = parse_search_rows(self.request.GET, BUNDLE_FIELD_DEFINITIONS)
        qs = apply_search_rows(qs, rows, BUNDLE_FIELD_DEFINITIONS)

        sort_key = self.request.GET.get("sort", "name")
        order = self.request.GET.get("order", "asc")

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

        sort_field = BUNDLE_SORT_ALLOWLIST.get(sort_key, "general_info__display_title")
        prefix = "-" if order == "desc" else ""
        qs = qs.order_by(f"{prefix}{sort_field}", "general_info__display_title")

        qs = qs.prefetch_related(
            "general_info",
            "general_info__keywords",
            "general_info__object_languages",
            "general_info__location",
            "structural_info",
            "structural_info__bundle_topics",
            "structural_info__is_member_of_collection",
            "structural_info__is_member_of_collection__general_info",
            "publication_info",
            "publication_info__creators",
            "publication_info__contributors__contributor_name",
        )

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        paginator = context.get("paginator")
        context["total_count"] = paginator.count if paginator else 0
        context["current_sort"] = self.request.GET.get("sort", "name")
        context["current_order"] = self.request.GET.get("order", "asc")
        context["current_params"] = self.request.GET.copy()

        rows = parse_search_rows(self.request.GET, BUNDLE_FIELD_DEFINITIONS)
        context["search_rows"] = rows
        context["has_search_rows"] = bool(rows)
        context["field_definitions"] = BUNDLE_FIELD_DEFINITIONS
        return context
