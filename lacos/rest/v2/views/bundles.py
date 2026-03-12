from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.serializers.jsonld import BLAM_CONTEXT
from lacos.rest.v2.access import build_access_denied_response, can_read_bundle
from lacos.rest.v2.query_params import build_next_url, parse_list_params
from lacos.rest.v2.resolvers import resolve_identifier
from lacos.rest.v2.serializers.bundles import (
    serialize_bundle_detail,
    serialize_bundle_list_item,
)


@extend_schema(
    summary="List bundles",
    description="Returns a paginated list of BLAM bundles with JSON-LD context. Optionally filter by collection.",
    tags=["bundles"],
    parameters=[
        OpenApiParameter("collection", OpenApiTypes.UUID, description="Filter by parent collection UUID"),
        OpenApiParameter("search", OpenApiTypes.STR, description="Full-text search query"),
        OpenApiParameter("ordering", OpenApiTypes.STR, description="Field to order by (prefix with - for descending)", default="-created_at"),
        OpenApiParameter("limit", OpenApiTypes.INT, description="Page size (max 100)", default=10),
        OpenApiParameter("offset", OpenApiTypes.INT, description="Number of items to skip", default=0),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def bundle_list(request):
    qs = Bundle.objects.prefetch_related(
        "general_info__keywords",
        "general_info__object_languages",
        "administrative_info",
        "structural_info__is_member_of_collection__general_info",
    ).all()

    collection = request.query_params.get("collection")
    if collection:
        qs = qs.filter(structural_info__is_member_of_collection__id=collection)

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(search_vector=search)

    params = parse_list_params(
        request.query_params,
        allowed_ordering={"identifier", "-identifier", "created_at", "-created_at"},
    )
    qs = qs.order_by(params.ordering)

    total = qs.count()
    page = qs[params.offset : params.offset + params.limit]

    results = [serialize_bundle_list_item(b) for b in page]

    next_url = build_next_url(
        request.query_params,
        limit=params.limit,
        offset=params.offset,
        total=total,
    )

    return Response(
        {
            "@context": BLAM_CONTEXT,
            "count": total,
            "next": next_url,
            "results": results,
        },
        content_type="application/ld+json",
    )


@extend_schema(
    summary="Get bundle detail",
    description="Returns full JSON-LD metadata for a single bundle. Accepts UUID or handle as identifier.",
    tags=["bundles"],
    parameters=[
        OpenApiParameter("identifier", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Bundle UUID or handle"),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def bundle_detail(request, identifier):
    bundle = resolve_identifier(Bundle, identifier)
    if not can_read_bundle(request.user, bundle):
        return build_access_denied_response(request.user)
    data = serialize_bundle_detail(bundle)
    return Response(data, content_type="application/ld+json")
