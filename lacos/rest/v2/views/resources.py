import uuid as uuid_mod
from urllib.parse import unquote

from django.contrib.contenttypes.models import ContentType
from django.http import Http404, HttpResponseRedirect
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from lacos.blam.models.bundle.bundle_structural_info import (
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.rest.v2.access import (
    build_access_denied_response,
    can_read_bundle,
    get_parent_bundle_or_404,
)
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.presigned_url_cache_service import PresignedUrlCacheService

RESOURCE_MODELS = [MediaResource, WrittenResource, OtherResource]


def _find_resource(identifier):
    """Find a resource across all resource types by UUID or file_pid."""
    decoded = unquote(identifier)

    for model in RESOURCE_MODELS:
        try:
            uid = uuid_mod.UUID(decoded)
            return model.objects.get(pk=uid)
        except (ValueError, model.DoesNotExist):
            pass
        try:
            return model.objects.get(file_pid=decoded)
        except model.DoesNotExist:
            pass

    raise Http404(f"Resource not found: {identifier}")

def _get_s3_location(resource):
    """Find S3 location for a resource."""
    ct = ContentType.objects.get_for_model(resource)
    try:
        return S3ResourceLocation.objects.get(content_type=ct, object_id=resource.id)
    except S3ResourceLocation.DoesNotExist:
        pass

    if resource.file_pid:
        try:
            return S3ResourceLocation.objects.get(resource_pid=resource.file_pid)
        except S3ResourceLocation.DoesNotExist:
            pass

    raise Http404("Resource file not mapped to storage")


def _build_auth_context(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"anon:{request.META.get('REMOTE_ADDR')}"


@extend_schema(
    summary="Get resource metadata",
    description="Returns metadata for a resource (media, written, or other). Accepts UUID or file PID as identifier.",
    tags=["resources"],
    parameters=[
        OpenApiParameter("identifier", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Resource UUID or file PID (handle)"),
    ],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def resource_detail(request, identifier):
    resource = _find_resource(identifier)
    bundle = get_parent_bundle_or_404(resource)
    if not can_read_bundle(request.user, bundle):
        return build_access_denied_response(request.user)

    data = {
        "@type": type(resource).__name__,
        "uuid": str(resource.id),
        "file_name": resource.file_name,
        "file_pid": resource.file_pid,
        "mime_type": resource.mime_type,
        "content_url": f"/api/v2/resources/{resource.id}/content/",
    }
    if hasattr(resource, "file_length") and resource.file_length:
        data["file_length"] = resource.file_length
    if hasattr(resource, "file_description") and resource.file_description:
        data["file_description"] = resource.file_description
    return Response(data, content_type="application/ld+json")


@extend_schema(
    summary="Get resource content",
    description="Redirects (302) to a presigned S3 URL for the resource file. Requires read access to the parent bundle.",
    tags=["resources"],
    parameters=[
        OpenApiParameter("identifier", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Resource UUID or file PID (handle)"),
    ],
    responses={302: None, 401: None, 403: None, 404: None},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def resource_content(request, identifier):
    resource = _find_resource(identifier)
    bundle = get_parent_bundle_or_404(resource)
    if not can_read_bundle(request.user, bundle):
        return build_access_denied_response(request.user)

    location = _get_s3_location(resource)

    cache_service = PresignedUrlCacheService()
    url_data = cache_service.get_download_url(
        bucket=location.s3_bucket,
        key=location.s3_key,
        filename=resource.file_name,
        auth_context=_build_auth_context(request),
    )
    return HttpResponseRedirect(url_data["url"])
