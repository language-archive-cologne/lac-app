from urllib.parse import unquote

from django.http import Http404, HttpResponseRedirect
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.presigned_url_cache_service import PresignedUrlCacheService

from .resources import _build_auth_context, _check_resource_access


@extend_schema(
    summary="Get media by handle",
    description="Resolves a PID handle directly to a presigned S3 URL (302 redirect). Shorthand for looking up a resource by handle and redirecting to its content.",
    tags=["media"],
    parameters=[
        OpenApiParameter("handle", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Resource PID handle (e.g. hdl:11341/0000-0000-0000-XXXX)"),
    ],
    responses={302: None, 401: None, 403: None, 404: None},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def media_by_handle(request, handle):
    """Resolve a handle directly to a presigned S3 URL (302 redirect)."""
    decoded = unquote(handle)

    try:
        location = S3ResourceLocation.objects.get(resource_pid=decoded)
    except S3ResourceLocation.DoesNotExist:
        raise Http404(f"No resource found for handle: {decoded}")

    if location.content_object:
        allowed, reason = _check_resource_access(
            location.content_object, request.user
        )
        if not allowed:
            if request.user.is_anonymous:
                return Response({"detail": "Authentication required"}, status=401)
            return Response({"detail": reason}, status=403)

    cache_service = PresignedUrlCacheService()
    filename = location.s3_key.rsplit("/", 1)[-1] if "/" in location.s3_key else location.s3_key

    url_data = cache_service.get_download_url(
        bucket=location.s3_bucket,
        key=location.s3_key,
        filename=filename,
        auth_context=_build_auth_context(request),
    )
    return HttpResponseRedirect(url_data["url"])
