"""Service for resolving bundle and collection resources to presigned URLs."""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from django.contrib.contenttypes.models import ContentType


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID format."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False

from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleAdditionalMetadataFile,
    BundleResources,
    MediaResource,
    OtherResource,
    WrittenResource,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.acl_evaluation_service import ACLEvaluationService
from lacos.storage.services.presigned_url_cache_service import (
    get_presigned_url_cache_service,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolvedResource:
    """Represents a successfully resolved resource with presigned URL."""

    resource_id: str
    bucket: str
    key: str
    filename: str
    size: int
    checksum: Optional[str]
    presigned_url: str


@dataclass
class ResourceError:
    """Represents an error when resolving a resource."""

    resource_id: str
    error: str  # "not_found", "not_in_bundle", "access_denied", "no_location"
    message: str


class ResourceResolverService:
    """
    Service for resolving resource IDs to presigned URLs.

    This service handles the complete flow of:
    1. Loading and validating the bundle
    2. Checking ACL permissions
    3. Verifying resources belong to the bundle
    4. Looking up S3 locations
    5. Generating presigned URLs
    """

    def __init__(self):
        self.acl_service = ACLEvaluationService()
        self.presigned_url_service = get_presigned_url_cache_service()

    def _build_auth_context(self, user) -> Optional[str]:
        if user and getattr(user, "is_authenticated", False):
            return f"user:{user.pk}"
        return None

    def resolve_resources(
        self,
        bundle_id: str,
        resource_ids: list[str],
        user,
    ) -> tuple[list[ResolvedResource], list[ResourceError]]:
        """
        Resolve resource IDs to presigned URLs.

        Args:
            bundle_id: The UUID of the bundle containing the resources
            resource_ids: List of resource IDs (UUIDs) to resolve
            user: The user requesting access (for ACL checks)

        Returns:
            Tuple of (resolved_resources, errors) where:
            - resolved_resources: List of ResolvedResource objects for successfully resolved resources
            - errors: List of ResourceError objects for resources that could not be resolved
        """
        resolved: list[ResolvedResource] = []
        errors: list[ResourceError] = []

        # 1. Validate bundle_id format
        if not is_valid_uuid(bundle_id):
            logger.warning(f"Invalid bundle UUID format: {bundle_id}")
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="bundle_not_found",
                        message=f"Bundle {bundle_id} not found",
                    )
                )
            return resolved, errors

        # 2. Load bundle
        try:
            bundle = Bundle.objects.get(id=bundle_id)
        except (Bundle.DoesNotExist, ValueError):
            logger.warning(f"Bundle not found: {bundle_id}")
            # Return error for all requested resources
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="bundle_not_found",
                        message=f"Bundle {bundle_id} not found",
                    )
                )
            return resolved, errors

        # 3. Check ACL permissions
        if not self.acl_service.is_allowed(user, bundle, mode="acl:Read"):
            logger.info(
                f"ACL denied for user {getattr(user, 'pk', 'anonymous')} on bundle {bundle_id}"
            )
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="access_denied",
                        message="Access denied to bundle resources",
                    )
                )
            return resolved, errors

        # 4. Get all resources belonging to this bundle
        bundle_resource_ids = self._get_bundle_resource_ids(bundle)

        # 5. Resolve each resource
        for resource_id in resource_ids:
            try:
                result = self._resolve_single_resource(
                    resource_id=resource_id,
                    bundle=bundle,
                    bundle_resource_ids=bundle_resource_ids,
                    user=user,
                )
                if isinstance(result, ResolvedResource):
                    resolved.append(result)
                else:
                    errors.append(result)
            except Exception as e:
                logger.exception(f"Unexpected error resolving resource {resource_id}")
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="internal_error",
                        message=str(e),
                    )
                )

        return resolved, errors

    def resolve_collection_resources(
        self,
        collection_id: str,
        resource_ids: list[str],
        user,
    ) -> tuple[list[ResolvedResource], list[ResourceError]]:
        """
        Resolve collection metadata file IDs to presigned URLs.

        Args:
            collection_id: The UUID of the collection
            resource_ids: List of resource IDs (UUIDs) to resolve
            user: The user requesting access (for ACL checks)

        Returns:
            Tuple of (resolved_resources, errors)
        """
        resolved: list[ResolvedResource] = []
        errors: list[ResourceError] = []

        # 1. Validate collection_id format
        if not is_valid_uuid(collection_id):
            logger.warning(f"Invalid collection UUID format: {collection_id}")
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="collection_not_found",
                        message=f"Collection {collection_id} not found",
                    )
                )
            return resolved, errors

        # 2. Load collection
        try:
            collection = Collection.objects.get(id=collection_id)
        except (Collection.DoesNotExist, ValueError):
            logger.warning(f"Collection not found: {collection_id}")
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="collection_not_found",
                        message=f"Collection {collection_id} not found",
                    )
                )
            return resolved, errors

        # 3. Check ACL permissions on collection
        if not self.acl_service.is_allowed(user, collection, mode="acl:Read"):
            logger.info(
                f"ACL denied for user {getattr(user, 'pk', 'anonymous')} on collection {collection_id}"
            )
            for resource_id in resource_ids:
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="access_denied",
                        message="Access denied to collection resources",
                    )
                )
            return resolved, errors

        # 4. Get all metadata file IDs belonging to this collection
        collection_resource_ids = self._get_collection_resource_ids(collection)

        # 5. Resolve each resource
        for resource_id in resource_ids:
            try:
                result = self._resolve_single_collection_resource(
                    resource_id=resource_id,
                    collection=collection,
                    collection_resource_ids=collection_resource_ids,
                    user=user,
                )
                if isinstance(result, ResolvedResource):
                    resolved.append(result)
                else:
                    errors.append(result)
            except Exception as e:
                logger.exception(f"Unexpected error resolving resource {resource_id}")
                errors.append(
                    ResourceError(
                        resource_id=resource_id,
                        error="internal_error",
                        message=str(e),
                    )
                )

        return resolved, errors

    def _get_collection_resource_ids(self, collection: Collection) -> set[str]:
        """Get all metadata file IDs that belong to a collection."""
        resource_ids: set[str] = set()

        try:
            structural_info = collection.structural_info.first()
            if not structural_info:
                logger.debug(f"No structural_info found for collection {collection.id}")
                return resource_ids

            for metadata_file in structural_info.additional_metadata_files.all():
                resource_ids.add(str(metadata_file.id))

        except Exception as e:
            logger.error(f"Error getting collection resource IDs: {e}")

        return resource_ids

    def _resolve_single_collection_resource(
        self,
        resource_id: str,
        collection: Collection,
        collection_resource_ids: set[str],
        user,
    ) -> ResolvedResource | ResourceError:
        """Resolve a single collection metadata file to a presigned URL."""
        # Verify resource belongs to collection
        if resource_id not in collection_resource_ids:
            return ResourceError(
                resource_id=resource_id,
                error="not_in_collection",
                message=f"Resource {resource_id} does not belong to collection {collection.id}",
            )

        # Find the metadata file
        try:
            metadata_file = CollectionAdditionalMetadataFile.objects.get(id=resource_id)
        except CollectionAdditionalMetadataFile.DoesNotExist:
            return ResourceError(
                resource_id=resource_id,
                error="not_found",
                message=f"Resource {resource_id} not found",
            )

        # Get S3 location
        location = self._get_s3_location(metadata_file)
        if location is None:
            return ResourceError(
                resource_id=resource_id,
                error="no_location",
                message=f"No S3 location found for resource {resource_id}",
            )

        # Generate presigned URL
        filename = metadata_file.file_name or location.s3_key.split("/")[-1]
        url_data = self.presigned_url_service.get_download_url(
            bucket=location.s3_bucket,
            key=location.s3_key,
            filename=filename,
            auth_context=self._build_auth_context(user),
        )

        size = location.size_bytes or 0

        return ResolvedResource(
            resource_id=resource_id,
            bucket=location.s3_bucket,
            key=location.s3_key,
            filename=filename,
            size=size,
            checksum=None,
            presigned_url=url_data["url"],
        )

    def _get_bundle_resource_ids(self, bundle: Bundle) -> set[str]:
        """
        Get all resource IDs that belong to a bundle.

        Returns a set of resource UUIDs (as strings) for all MediaResource,
        WrittenResource, OtherResource, and BundleAdditionalMetadataFile objects
        linked to this bundle.
        """
        resource_ids: set[str] = set()

        try:
            bundle_resources = BundleResources.objects.filter(bundle=bundle).first()
            if bundle_resources:
                # Collect IDs from all bundle resource types
                for media_resource in bundle_resources.bundle_media_resources.all():
                    resource_ids.add(str(media_resource.id))

                for written_resource in bundle_resources.bundle_written_resources.all():
                    resource_ids.add(str(written_resource.id))

                for other_resource in bundle_resources.bundle_other_resources.all():
                    resource_ids.add(str(other_resource.id))
            else:
                logger.debug(f"No BundleResources found for bundle {bundle.id}")

            structural_info = bundle.structural_info.first()
            if structural_info:
                for metadata_file in structural_info.additional_metadata_files.all():
                    resource_ids.add(str(metadata_file.id))

        except Exception as e:
            logger.error(f"Error getting bundle resource IDs: {e}")

        return resource_ids

    def _resolve_single_resource(
        self,
        resource_id: str,
        bundle: Bundle,
        bundle_resource_ids: set[str],
        user,
    ) -> ResolvedResource | ResourceError:
        """
        Resolve a single resource ID to a presigned URL.

        Args:
            resource_id: The UUID of the resource
            bundle: The bundle object
            bundle_resource_ids: Set of resource IDs that belong to the bundle
            user: The user requesting access (for cache scoping)

        Returns:
            ResolvedResource on success, ResourceError on failure
        """
        # Verify resource belongs to bundle
        if resource_id not in bundle_resource_ids:
            return ResourceError(
                resource_id=resource_id,
                error="not_in_bundle",
                message=f"Resource {resource_id} does not belong to bundle {bundle.id}",
            )

        # Find the resource object
        resource = self._find_resource_by_id(resource_id)
        if resource is None:
            return ResourceError(
                resource_id=resource_id,
                error="not_found",
                message=f"Resource {resource_id} not found",
            )

        # Get S3 location
        location = self._get_s3_location(resource)
        if location is None:
            return ResourceError(
                resource_id=resource_id,
                error="no_location",
                message=f"No S3 location found for resource {resource_id}",
            )

        # Generate presigned URL
        filename = getattr(resource, "file_name", "") or location.s3_key.split("/")[-1]
        url_data = self.presigned_url_service.get_download_url(
            bucket=location.s3_bucket,
            key=location.s3_key,
            filename=filename,
            auth_context=self._build_auth_context(user),
        )

        # Get size from location or default to 0
        size = location.size_bytes or 0

        return ResolvedResource(
            resource_id=resource_id,
            bucket=location.s3_bucket,
            key=location.s3_key,
            filename=filename,
            size=size,
            checksum=None,  # Checksum not currently stored in S3ResourceLocation
            presigned_url=url_data["url"],
        )

    def _find_resource_by_id(
        self, resource_id: str
    ) -> MediaResource | WrittenResource | OtherResource | BundleAdditionalMetadataFile | None:
        """
        Find a resource by its UUID across all resource types.

        Args:
            resource_id: The UUID of the resource

        Returns:
            The resource object if found, None otherwise
        """
        # Try each resource type
        try:
            return MediaResource.objects.get(id=resource_id)
        except MediaResource.DoesNotExist:
            pass

        try:
            return WrittenResource.objects.get(id=resource_id)
        except WrittenResource.DoesNotExist:
            pass

        try:
            return OtherResource.objects.get(id=resource_id)
        except OtherResource.DoesNotExist:
            pass

        try:
            return BundleAdditionalMetadataFile.objects.get(id=resource_id)
        except BundleAdditionalMetadataFile.DoesNotExist:
            pass

        return None

    def _get_s3_location(
        self,
        resource: MediaResource | WrittenResource | OtherResource | BundleAdditionalMetadataFile,
    ) -> S3ResourceLocation | None:
        """
        Get the S3 location for a resource.

        Args:
            resource: The resource object

        Returns:
            S3ResourceLocation if found, None otherwise
        """
        try:
            content_type = ContentType.objects.get_for_model(resource)
            return S3ResourceLocation.objects.get(
                content_type=content_type,
                object_id=str(resource.id),
            )
        except S3ResourceLocation.DoesNotExist:
            logger.debug(
                f"No S3ResourceLocation found for {type(resource).__name__} {resource.id}"
            )
            return None
