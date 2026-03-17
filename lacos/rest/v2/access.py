from django.http import Http404
from django.contrib.contenttypes.models import ContentType
from rest_framework.response import Response

from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.acl_permissions import ACLPermissions
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService


def build_access_denied_response(user, detail: str = "access denied") -> Response:
    if getattr(user, "is_anonymous", True):
        return Response({"detail": "Authentication required"}, status=401)
    return Response({"detail": detail}, status=403)


def can_read_bundle(user, bundle) -> bool:
    service = ACLEvaluationService()
    return service.can_read_bundle(user, bundle)


def can_read_collection(user, collection: Collection) -> bool:
    service = ACLEvaluationService()
    return service.can_read_collection(user, collection)


def filter_readable_collections(user, collections: list[Collection]) -> list[Collection]:
    _attach_acl_permissions(collections)
    service = ACLEvaluationService()
    return [collection for collection in collections if service.can_read_collection(user, collection)]


def filter_readable_bundles(user, bundles: list) -> list:
    _attach_acl_permissions(bundles)
    parent_collections = []
    for bundle in bundles:
        structural = getattr(bundle, "structural_info", None)
        if structural is None:
            continue
        relation = structural.first()
        if relation and relation.is_member_of_collection:
            bundle._acl_parent = relation.is_member_of_collection
            parent_collections.append(relation.is_member_of_collection)

    _attach_acl_permissions(parent_collections)
    service = ACLEvaluationService()
    return [bundle for bundle in bundles if service.can_read_bundle(user, bundle)]


def _attach_acl_permissions(objects: list) -> None:
    if not objects:
        return

    objects_by_model = {}
    for obj in objects:
        objects_by_model.setdefault(type(obj), []).append(obj)

    for model, model_objects in objects_by_model.items():
        content_type = ContentType.objects.get_for_model(model)
        object_ids = [str(obj.pk) for obj in model_objects]
        permissions = ACLPermissions.objects.filter(
            content_type=content_type,
            object_id__in=object_ids,
        ).order_by("id")
        permission_by_id = {}
        for permission in permissions:
            permission_by_id.setdefault(str(permission.object_id), permission)
        for obj in model_objects:
            obj._acl_permissions = permission_by_id.get(str(obj.pk))


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
