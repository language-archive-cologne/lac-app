from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.serializers.jsonld import BLAM_CONTEXT
from lacos.rest.v2.query_params import build_next_url, parse_list_params
from lacos.rest.v2.resolvers import resolve_identifier
from lacos.rest.v2.serializers.collections import (
    serialize_collection_detail,
    serialize_collection_list_item,
)
from lacos.storage.services.exposure_policy_service import ExposurePolicyService


@extend_schema(
    summary="List collections",
    description="Returns a paginated list of BLAM collections with JSON-LD context.",
    tags=["collections"],
    parameters=[
        OpenApiParameter("search", OpenApiTypes.STR, description="Full-text search query"),
        OpenApiParameter("ordering", OpenApiTypes.STR, description="Field to order by (prefix with - for descending)", default="-created_at"),
        OpenApiParameter("limit", OpenApiTypes.INT, description="Page size (max 100)", default=10),
        OpenApiParameter("offset", OpenApiTypes.INT, description="Number of items to skip", default=0),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def collection_list(request):
    policy = ExposurePolicyService()
    qs = Collection.objects.prefetch_related(
        "general_info__keywords",
        "general_info__object_languages",
        "administrative_info",
    ).all()
    qs = policy.filter_collection_queryset(request.user, qs, channel="api")

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(search_vector=search)

    params = parse_list_params(
        request.query_params,
        allowed_ordering={"identifier", "-identifier", "created_at", "-created_at"},
    )
    qs = qs.order_by(params.ordering)

    collections = list(qs)
    total = len(collections)
    page = collections[params.offset : params.offset + params.limit]

    results = [serialize_collection_list_item(c) for c in page]

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
    summary="Get collection detail",
    description="Returns full JSON-LD metadata for a single collection. Accepts UUID or handle as identifier.",
    tags=["collections"],
    parameters=[
        OpenApiParameter("identifier", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Collection UUID or handle"),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def collection_detail(request, identifier):
    policy = ExposurePolicyService()
    collection = resolve_identifier(Collection, identifier)
    if not policy.can_view_metadata(request.user, collection):
        return Response({"detail": "access denied"}, status=403)
    data = serialize_collection_detail(collection)
    return Response(data, content_type="application/ld+json")
