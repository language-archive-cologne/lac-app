import logging
from django.db.models.signals import m2m_changed, pre_delete, post_delete, post_save
from django.dispatch import receiver
# Import the necessary models
from .models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from .models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from .models.bundle.bundle_publication_info import BundlePublicationInfo
from .models.bundle.bundle_structural_info import BundleStructuralInfo, MediaResource, WrittenResource, OtherResource
from .models.bundle.bundle_repository import Bundle
from .models.collection.collection_repository import Collection
from .models.collection.collection_administrative_info import CollectionAdministrativeInfo
from .models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from .models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.storage.models import S3ResourceLocation
from lacos.storage.models.acl_permissions import ACLPermissions
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)
security_logger = logging.getLogger("lacos.security")


def _invalidate_explorer_caches():
    """Invalidate explorer caches when collection data changes."""
    from lacos.explorer.map_utils import invalidate_map_markers_cache
    from lacos.explorer.facets import FacetService
    from django.core.cache import cache
    invalidate_map_markers_cache()
    cache.delete("explorer:language_count")
    FacetService.invalidate_cache()
    logger.debug("Explorer caches invalidated")


def _is_post_m2m_action(action: str | None) -> bool:
    """Return whether an m2m_changed action represents committed data."""
    return action in {"post_add", "post_remove", "post_clear"}




@receiver(pre_delete, sender=BundleStructuralInfo)
def delete_associated_resources(sender, instance, **kwargs):
    """
    Signal handler to delete associated MediaResource, WrittenResource, 
    and OtherResource objects BEFORE a BundleStructuralInfo object is deleted.
    """
    try:
        # instance is the BundleStructuralInfo object being deleted
        try:
            # Use getattr with a default of None to handle cases where the relation doesn't exist
            resources_container = getattr(instance, 'resources', None)
        except Exception as e:
            logger.warning("Could not access resources for BundleStructuralInfo", extra={"pk": instance.pk, "error": e})
            resources_container = None
        
        if resources_container:
            logger.info("PRE_DELETE signal: Deleting resources for BundleStructuralInfo", extra={"structural_info_pk": instance.pk, "bundle_resources_pk": resources_container.pk})

            # Get all related resource objects (convert to list before deleting)
            media_resources = list(resources_container.bundle_media_resources.all())
            written_resources = list(resources_container.bundle_written_resources.all())
            other_resources = list(resources_container.bundle_other_resources.all())

            # Delete Media Resources
            if media_resources:
                logger.info("Deleting MediaResources", extra={"count": len(media_resources)})
                for resource in media_resources:
                    resource.delete() 

            # Delete Written Resources
            if written_resources:
                logger.info("Deleting WrittenResources", extra={"count": len(written_resources)})
                for resource in written_resources:
                    resource.delete()

            # Delete Other Resources
            if other_resources:
                logger.info("Deleting OtherResources", extra={"count": len(other_resources)})
                for resource in other_resources:
                    resource.delete()
            
            # Explicitly delete the BundleResources container itself 
            # because CASCADE doesn't seem to be working properly
            logger.info("Explicitly deleting BundleResources container", extra={"pk": resources_container.pk})
            resources_container_pk = resources_container.pk
            resources_container.delete()
            logger.info("Successfully deleted BundleResources container", extra={"pk": resources_container_pk})
            
            logger.info("Finished deleting associated resources for BundleStructuralInfo", extra={"pk": instance.pk})
            # The comment below is incorrect - CASCADE is not working as expected, so we delete it explicitly above
            # The BundleResources container itself will be deleted after this by CASCADE

        else:
            logger.warning("PRE_DELETE signal for BundleStructuralInfo, but no associated BundleResources container found", extra={"pk": instance.pk})

    except Exception as e:
        logger.error("Error in pre_delete signal for BundleStructuralInfo", extra={"pk": instance.pk, "error": e}, exc_info=True)

# Add signal handlers for each resource type to delete S3ResourceLocation objects
@receiver(pre_delete, sender=MediaResource)
def delete_s3_locations_for_media_resource(sender, instance, **kwargs):
    """
    Signal handler to delete associated S3ResourceLocation objects
    when a MediaResource is deleted.
    """
    try:
        # Get the resource PID
        resource_pid = instance.file_pid
        if resource_pid:
            # Find all S3ResourceLocation objects with this PID
            s3_locations = S3ResourceLocation.objects.filter(resource_pid=resource_pid)
            count = s3_locations.count()
            
            if count > 0:
                logger.info("PRE_DELETE signal: Deleting S3ResourceLocations for MediaResource", extra={"count": count, "pk": instance.pk, "resource_pid": resource_pid})
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info("Successfully deleted S3ResourceLocations for MediaResource", extra={"deleted_count": deleted_count, "pk": instance.pk})
            else:
                logger.info("No S3ResourceLocation objects found for MediaResource", extra={"pk": instance.pk, "resource_pid": resource_pid})
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this MediaResource by content_type/object_id
        media_content_type = ContentType.objects.get_for_model(MediaResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=media_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info("Also deleting S3ResourceLocations by content reference for MediaResource", extra={"count": count, "pk": instance.pk})
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error("Error in pre_delete signal for MediaResource", extra={"pk": instance.pk, "error": e}, exc_info=True)

@receiver(pre_delete, sender=WrittenResource)
def delete_s3_locations_for_written_resource(sender, instance, **kwargs):
    """
    Signal handler to delete associated S3ResourceLocation objects
    when a WrittenResource is deleted.
    """
    try:
        # Get the resource PID
        resource_pid = instance.file_pid
        if resource_pid:
            # Find all S3ResourceLocation objects with this PID
            s3_locations = S3ResourceLocation.objects.filter(resource_pid=resource_pid)
            count = s3_locations.count()
            
            if count > 0:
                logger.info("PRE_DELETE signal: Deleting S3ResourceLocations for WrittenResource", extra={"count": count, "pk": instance.pk, "resource_pid": resource_pid})
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info("Successfully deleted S3ResourceLocations for WrittenResource", extra={"deleted_count": deleted_count, "pk": instance.pk})
            else:
                logger.info("No S3ResourceLocation objects found for WrittenResource", extra={"pk": instance.pk, "resource_pid": resource_pid})
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this WrittenResource by content_type/object_id
        written_content_type = ContentType.objects.get_for_model(WrittenResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=written_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info("Also deleting S3ResourceLocations by content reference for WrittenResource", extra={"count": count, "pk": instance.pk})
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error("Error in pre_delete signal for WrittenResource", extra={"pk": instance.pk, "error": e}, exc_info=True)

@receiver(pre_delete, sender=OtherResource)
def delete_s3_locations_for_other_resource(sender, instance, **kwargs):
    """
    Signal handler to delete associated S3ResourceLocation objects
    when an OtherResource is deleted.
    """
    try:
        # Get the resource PID
        resource_pid = instance.file_pid
        if resource_pid:
            # Find all S3ResourceLocation objects with this PID
            s3_locations = S3ResourceLocation.objects.filter(resource_pid=resource_pid)
            count = s3_locations.count()
            
            if count > 0:
                logger.info("PRE_DELETE signal: Deleting S3ResourceLocations for OtherResource", extra={"count": count, "pk": instance.pk, "resource_pid": resource_pid})
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info("Successfully deleted S3ResourceLocations for OtherResource", extra={"deleted_count": deleted_count, "pk": instance.pk})
            else:
                logger.info("No S3ResourceLocation objects found for OtherResource", extra={"pk": instance.pk, "resource_pid": resource_pid})
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this OtherResource by content_type/object_id
        other_content_type = ContentType.objects.get_for_model(OtherResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=other_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info("Also deleting S3ResourceLocations by content reference for OtherResource", extra={"count": count, "pk": instance.pk})
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error("Error in pre_delete signal for OtherResource", extra={"pk": instance.pk, "error": e}, exc_info=True)


# Security audit logging for critical model deletions
@receiver(post_delete, sender=Collection)
def log_collection_deletion(sender, instance, **kwargs):
    """Log collection deletion for security audit."""
    collection_name = getattr(instance, "name", "unknown")
    collection_pid = getattr(instance, "pid", "unknown")
    security_logger.warning(
        "COLLECTION_DELETED",
        extra={"collection_name": collection_name, "pid": collection_pid, "pk": instance.pk},
    )
    _invalidate_explorer_caches()


@receiver(post_save, sender=Collection)
def invalidate_cache_on_collection_save(sender, instance, **kwargs):
    """Invalidate explorer caches when a collection is created or updated."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=CollectionGeneralInfo)
def invalidate_cache_on_general_info_save(sender, instance, **kwargs):
    """Invalidate explorer caches when collection general info changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=CollectionLocation)
@receiver(post_delete, sender=CollectionLocation)
def invalidate_cache_on_location_change(sender, instance, **kwargs):
    """Invalidate explorer caches when collection location changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=CollectionPublicationInfo)
@receiver(post_delete, sender=CollectionPublicationInfo)
def invalidate_cache_on_collection_publication_info_change(sender, instance, **kwargs):
    """Invalidate explorer caches when collection publication info changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=CollectionAdministrativeInfo)
@receiver(post_delete, sender=CollectionAdministrativeInfo)
def invalidate_cache_on_collection_admin_info_change(sender, instance, **kwargs):
    """Invalidate explorer caches when collection administrative info changes."""
    _invalidate_explorer_caches()


@receiver(m2m_changed, sender=CollectionGeneralInfo.keywords.through)
@receiver(m2m_changed, sender=CollectionGeneralInfo.object_languages.through)
def invalidate_cache_on_collection_general_info_m2m_change(
    sender,
    instance,
    action,
    **kwargs,
):
    """Invalidate explorer caches when collection keywords or languages change."""
    if _is_post_m2m_action(action):
        _invalidate_explorer_caches()


@receiver(m2m_changed, sender=CollectionAdministrativeInfo.licenses.through)
def invalidate_cache_on_collection_licenses_change(sender, instance, action, **kwargs):
    """Invalidate explorer caches when collection licenses change."""
    if _is_post_m2m_action(action):
        _invalidate_explorer_caches()


@receiver(post_save, sender=ACLPermissions)
@receiver(post_delete, sender=ACLPermissions)
def invalidate_cache_on_acl_permission_change(sender, instance, **kwargs):
    """Invalidate explorer caches when indexed access levels change."""
    _invalidate_explorer_caches()


@receiver(post_delete, sender=Bundle)
def log_bundle_deletion(sender, instance, **kwargs):
    """Log bundle deletion for security audit."""
    bundle_name = getattr(instance, "name", "unknown")
    bundle_pid = getattr(instance, "pid", "unknown")
    security_logger.warning(
        "BUNDLE_DELETED",
        extra={"bundle_name": bundle_name, "pid": bundle_pid, "pk": instance.pk},
    )
    _invalidate_explorer_caches()


@receiver(post_save, sender=Bundle)
def invalidate_cache_on_bundle_save(sender, instance, **kwargs):
    """Invalidate explorer caches when a bundle is created or updated."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=BundleGeneralInfo)
def invalidate_cache_on_bundle_general_info_save(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle general info changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=BundleLocation)
@receiver(post_delete, sender=BundleLocation)
def invalidate_cache_on_bundle_location_change(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle location changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=BundleStructuralInfo)
def invalidate_cache_on_bundle_structural_info_save(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle structural info changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=BundlePublicationInfo)
@receiver(post_delete, sender=BundlePublicationInfo)
def invalidate_cache_on_bundle_publication_info_change(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle publication info changes."""
    _invalidate_explorer_caches()


@receiver(post_save, sender=BundleAdministrativeInfo)
@receiver(post_delete, sender=BundleAdministrativeInfo)
def invalidate_cache_on_bundle_admin_info_change(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle administrative info changes."""
    _invalidate_explorer_caches()


@receiver(m2m_changed, sender=BundleGeneralInfo.keywords.through)
@receiver(m2m_changed, sender=BundleGeneralInfo.object_languages.through)
def invalidate_cache_on_bundle_general_info_m2m_change(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle keywords or languages change."""
    _invalidate_explorer_caches()



@receiver(m2m_changed, sender=BundleAdministrativeInfo.licenses.through)
def invalidate_cache_on_bundle_licenses_change(sender, instance, **kwargs):
    """Invalidate explorer caches when bundle licenses change."""
    _invalidate_explorer_caches()
