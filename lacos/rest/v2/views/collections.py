from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.serializers.jsonld import BLAM_CONTEXT
from lacos.rest.v2.resolvers import resolve_identifier
from lacos.rest.v2.serializers.collections import (
    serialize_collection_detail,
    serialize_collection_list_item,
)


@api_view(["GET"])
@permission_classes([AllowAny])
def collection_list(request):
    qs = Collection.objects.prefetch_related(
        "general_info__keywords",
        "general_info__object_languages",
        "administrative_info",
    ).all()

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(search_vector=search)

    ordering = request.query_params.get("ordering", "-created_at")
    qs = qs.order_by(ordering)

    limit = min(int(request.query_params.get("limit", 10)), 100)
    offset = int(request.query_params.get("offset", 0))
    total = qs.count()
    page = qs[offset : offset + limit]

    results = [serialize_collection_list_item(c) for c in page]

    next_url = None
    if offset + limit < total:
        next_url = f"?limit={limit}&offset={offset + limit}"

    return Response(
        {
            "@context": BLAM_CONTEXT,
            "count": total,
            "next": next_url,
            "results": results,
        },
        content_type="application/ld+json",
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def collection_detail(request, identifier):
    collection = resolve_identifier(Collection, identifier)
    data = serialize_collection_detail(collection)
    return Response(data, content_type="application/ld+json")
