from __future__ import annotations

from typing import Any, Literal

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService

DiscoverabilityChannel = Literal["browse", "search", "sitemap", "oai", "api"]

RESOURCE_MODELS = (MediaResource, WrittenResource, OtherResource)
PUBLIC_METADATA_FILE_MODELS = (
    CollectionAdditionalMetadataFile,
    BundleAdditionalMetadataFile,
)


class ExposurePolicyService:
    """
    Central policy service for public metadata visibility and binary access.

    Current policy:
    - Collection, bundle, and resource metadata are public.
    - Collection and bundle additional metadata files are public.
    - Actual bundle/resource binaries require bundle read access.
    - Discoverability surfaces (search, sitemap, OAI, list APIs) follow the
      same metadata visibility policy.
    """

    def __init__(self, acl_service: ACLEvaluationService | None = None):
        self._acl_service = acl_service

    @property
    def acl_service(self) -> ACLEvaluationService:
        if self._acl_service is None:
            self._acl_service = ACLEvaluationService()
        return self._acl_service

    def can_view_metadata(self, user, obj: Any) -> bool:
        if isinstance(obj, (Collection, Bundle, *RESOURCE_MODELS, *PUBLIC_METADATA_FILE_MODELS)):
            return True
        return False

    def can_download_binary(self, user, obj: Any) -> bool:
        if isinstance(obj, PUBLIC_METADATA_FILE_MODELS):
            return True

        target = obj
        if isinstance(obj, S3ResourceLocation):
            target = obj.content_object
            if target is None:
                return False

        if isinstance(target, PUBLIC_METADATA_FILE_MODELS):
            return True

        if isinstance(target, Bundle):
            return self.acl_service.can_read_bundle(user, target)

        if isinstance(target, RESOURCE_MODELS):
            bundle = self._get_resource_bundle(target)
            if bundle is None:
                return False
            return self.acl_service.can_read_bundle(user, bundle)

        return False

    def can_list_in_search(self, user, obj: Any) -> bool:
        return self.can_view_metadata(user, obj)

    def can_appear_in_sitemap(self, user, obj: Any) -> bool:
        return self.can_view_metadata(user, obj)

    def can_harvest_via_oai(self, user, obj: Any) -> bool:
        return self.can_view_metadata(user, obj)

    def filter_collection_queryset(
        self,
        user,
        queryset: QuerySet[Collection],
        *,
        channel: DiscoverabilityChannel,
    ) -> QuerySet[Collection]:
        del user, channel
        return queryset

    def filter_bundle_queryset(
        self,
        user,
        queryset: QuerySet[Bundle],
        *,
        channel: DiscoverabilityChannel,
    ) -> QuerySet[Bundle]:
        del user, channel
        return queryset

    @staticmethod
    def anonymous_user():
        return AnonymousUser()

    @staticmethod
    def _get_resource_bundle(resource) -> Bundle | None:
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

        return relation.bundle if relation else None
