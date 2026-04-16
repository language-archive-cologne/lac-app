import logging
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
    ensure_metadata_exposed,
    ensure_resource_binary_exposed,
    get_parent_bundle_or_404,
)
from lacos.explorer.media_utils import determine_media_type, guess_source_mime_type
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.presigned_url_cache_service import PresignedUrlCacheService

logger = logging.getLogger(__name__)

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


def _resource_download_path(resource) -> str:
    return f"/api/v2/resources/{resource.id}/content/"


def _resource_stream_path(resource) -> str:
    return f"/api/v2/resources/{resource.id}/stream/"


def _resource_media_type(resource) -> str | None:
    return determine_media_type(resource.mime_type, resource.file_name)


def _stream_response_headers(resource) -> dict:
    media_type = _resource_media_type(resource)
    source_mime_type = guess_source_mime_type(
        resource.mime_type,
        resource.file_name,
        media_type,
    )
    return {"ResponseContentType": source_mime_type} if source_mime_type else {}


def _stream_supported(resource) -> bool:
    return _resource_media_type(resource) in {"audio", "video"}

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
    get_parent_bundle_or_404(resource)
    denied_response = ensure_metadata_exposed(request.user, resource)
    if denied_response is not None:
        return denied_response

    data = {
        "@type": type(resource).__name__,
        "uuid": str(resource.id),
        "file_name": resource.file_name,
        "file_pid": resource.file_pid,
        "mime_type": resource.mime_type,
        "content_url": _resource_download_path(resource),
        "download_url": _resource_download_path(resource),
    }
    if _stream_supported(resource):
        data["stream_url"] = _resource_stream_path(resource)
    if hasattr(resource, "file_length") and resource.file_length:
        data["file_length"] = resource.file_length
    if hasattr(resource, "file_description") and resource.file_description:
        data["file_description"] = resource.file_description

    try:
        location = _get_s3_location(resource)
        if location.size_bytes is None:
            info = BucketService().get_file_info(location.s3_bucket, location.s3_key)
            if info.get("success") and info.get("file_size"):
                location.size_bytes = info["file_size"]
                location.save(update_fields=["size_bytes"])
        if location.size_bytes is not None:
            data["size_bytes"] = location.size_bytes
    except Exception:
        logger.warning("Could not resolve size_bytes for resource %s", identifier)

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
    denied_response = ensure_resource_binary_exposed(request, resource)
    if denied_response is not None:
        return denied_response

    location = _get_s3_location(resource)

    cache_service = PresignedUrlCacheService()
    url_data = cache_service.get_download_url(
        bucket=location.s3_bucket,
        key=location.s3_key,
        filename=resource.file_name,
        auth_context=_build_auth_context(request),
    )
    return HttpResponseRedirect(url_data["url"])


@extend_schema(
    summary="Get streamable resource content",
    description="Redirects (302) to a presigned inline URL for audio or video playback. Requires read access to the parent bundle.",
    tags=["resources"],
    parameters=[
        OpenApiParameter("identifier", OpenApiTypes.STR, location=OpenApiParameter.PATH, description="Resource UUID or file PID (handle)"),
    ],
    responses={302: None, 401: None, 403: None, 404: None},
)
@api_view(["GET"])
@permission_classes([AllowAny])
def resource_stream(request, identifier):
    resource = _find_resource(identifier)
    if not _stream_supported(resource):
        raise Http404(f"Streaming not supported for resource: {identifier}")

    denied_response = ensure_resource_binary_exposed(request, resource)
    if denied_response is not None:
        return denied_response

    location = _get_s3_location(resource)

    cache_service = PresignedUrlCacheService()
    url = cache_service.get_presigned_url(
        bucket=location.s3_bucket,
        key=location.s3_key,
        response_headers=_stream_response_headers(resource),
        auth_context=_build_auth_context(request),
    )
    return HttpResponseRedirect(url)
