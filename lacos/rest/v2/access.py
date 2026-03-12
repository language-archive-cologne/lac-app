from django.http import Http404
from rest_framework.response import Response

from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService


def build_access_denied_response(user, detail: str = "access denied") -> Response:
    if getattr(user, "is_anonymous", True):
        return Response({"detail": "Authentication required"}, status=401)
    return Response({"detail": detail}, status=403)


def can_read_bundle(user, bundle) -> bool:
    service = ACLEvaluationService()
    return service.can_read_bundle(user, bundle)


def get_parent_bundle_or_404(resource):
    bundle_resources = getattr(resource, "bundleresources_set", None)
    if bundle_resources is not None:
        relation = bundle_resources.first()
        if relation:
            return relation.bundle

    if isinstance(resource, MediaResource):
        relation = BundleResources.objects.filter(bundle_media_resources=resource).first()
    elif isinstance(resource, WrittenResource):
        relation = BundleResources.objects.filter(bundle_written_resources=resource).first()
    elif isinstance(resource, OtherResource):
        relation = BundleResources.objects.filter(bundle_other_resources=resource).first()
    else:
        relation = None

    if relation:
        return relation.bundle

    raise Http404("Resource is not linked to a bundle")
