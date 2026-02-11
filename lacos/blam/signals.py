import logging
from django.db.models.signals import pre_delete, post_delete, post_save
from django.dispatch import receiver
# Import the necessary models
from .models.bundle.bundle_structural_info import BundleStructuralInfo, MediaResource, WrittenResource, OtherResource
from .models.bundle.bundle_repository import Bundle
from .models.collection.collection_repository import Collection
from .models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.storage.models import S3ResourceLocation
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
            logger.warning(f"Could not access resources for BundleStructuralInfo PK={instance.pk}: {e}")
            resources_container = None
        
        if resources_container:
            logger.info(f"PRE_DELETE signal: Deleting resources for BundleStructuralInfo PK={instance.pk} via BundleResources PK={resources_container.pk}")

            # Get all related resource objects (convert to list before deleting)
            media_resources = list(resources_container.bundle_media_resources.all())
            written_resources = list(resources_container.bundle_written_resources.all())
            other_resources = list(resources_container.bundle_other_resources.all())

            # Delete Media Resources
            if media_resources:
                logger.info(f"Deleting {len(media_resources)} MediaResource(s)...")
                for resource in media_resources:
                    resource.delete() 

            # Delete Written Resources
            if written_resources:
                logger.info(f"Deleting {len(written_resources)} WrittenResource(s)...")
                for resource in written_resources:
                    resource.delete()

            # Delete Other Resources
            if other_resources:
                logger.info(f"Deleting {len(other_resources)} OtherResource(s)...")
                for resource in other_resources:
                    resource.delete()
            
            # Explicitly delete the BundleResources container itself 
            # because CASCADE doesn't seem to be working properly
            logger.info(f"Explicitly deleting BundleResources container PK={resources_container.pk}")
            resources_container_pk = resources_container.pk
            resources_container.delete()
            logger.info(f"Successfully deleted BundleResources container PK={resources_container_pk}")
            
            logger.info(f"Finished deleting associated resources for BundleStructuralInfo PK={instance.pk}")
            # The comment below is incorrect - CASCADE is not working as expected, so we delete it explicitly above
            # The BundleResources container itself will be deleted after this by CASCADE

        else:
            logger.warning(f"PRE_DELETE signal for BundleStructuralInfo PK={instance.pk}, but no associated BundleResources container found.")

    except Exception as e:
        logger.error(f"Error in pre_delete signal for BundleStructuralInfo PK={instance.pk}: {e}", exc_info=True)

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
                logger.info(f"PRE_DELETE signal: Deleting {count} S3ResourceLocation(s) for MediaResource PK={instance.pk} (PID={resource_pid})")
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info(f"Successfully deleted {deleted_count} S3ResourceLocation(s) for MediaResource PK={instance.pk}")
            else:
                logger.info(f"No S3ResourceLocation objects found for MediaResource PK={instance.pk} (PID={resource_pid})")
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this MediaResource by content_type/object_id
        media_content_type = ContentType.objects.get_for_model(MediaResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=media_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info(f"Also deleting {count} S3ResourceLocation(s) by content reference for MediaResource PK={instance.pk}")
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error(f"Error in pre_delete signal for MediaResource PK={instance.pk}: {e}", exc_info=True)

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
                logger.info(f"PRE_DELETE signal: Deleting {count} S3ResourceLocation(s) for WrittenResource PK={instance.pk} (PID={resource_pid})")
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info(f"Successfully deleted {deleted_count} S3ResourceLocation(s) for WrittenResource PK={instance.pk}")
            else:
                logger.info(f"No S3ResourceLocation objects found for WrittenResource PK={instance.pk} (PID={resource_pid})")
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this WrittenResource by content_type/object_id
        written_content_type = ContentType.objects.get_for_model(WrittenResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=written_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info(f"Also deleting {count} S3ResourceLocation(s) by content reference for WrittenResource PK={instance.pk}")
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error(f"Error in pre_delete signal for WrittenResource PK={instance.pk}: {e}", exc_info=True)

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
                logger.info(f"PRE_DELETE signal: Deleting {count} S3ResourceLocation(s) for OtherResource PK={instance.pk} (PID={resource_pid})")
                # Use a more direct approach to ensure deletion
                deleted_count = s3_locations.delete()[0]
                logger.info(f"Successfully deleted {deleted_count} S3ResourceLocation(s) for OtherResource PK={instance.pk}")
            else:
                logger.info(f"No S3ResourceLocation objects found for OtherResource PK={instance.pk} (PID={resource_pid})")
        
        # As a fallback, also try to delete any S3ResourceLocation referencing this OtherResource by content_type/object_id
        other_content_type = ContentType.objects.get_for_model(OtherResource)
        s3_by_obj = S3ResourceLocation.objects.filter(
            content_type=other_content_type,
            object_id=str(instance.pk)
        )
        if s3_by_obj.exists():
            count = s3_by_obj.count()
            logger.info(f"Also deleting {count} S3ResourceLocation(s) by content reference for OtherResource PK={instance.pk}")
            s3_by_obj.delete()
            
    except Exception as e:
        logger.error(f"Error in pre_delete signal for OtherResource PK={instance.pk}: {e}", exc_info=True)


# Security audit logging for critical model deletions
@receiver(post_delete, sender=Collection)
def log_collection_deletion(sender, instance, **kwargs):
    """Log collection deletion for security audit."""
    collection_name = getattr(instance, "name", "unknown")
    collection_pid = getattr(instance, "pid", "unknown")
    security_logger.warning(
        f"COLLECTION_DELETED: name={collection_name} pid={collection_pid} pk={instance.pk}"
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


@receiver(post_delete, sender=Bundle)
def log_bundle_deletion(sender, instance, **kwargs):
    """Log bundle deletion for security audit."""
    bundle_name = getattr(instance, "name", "unknown")
    bundle_pid = getattr(instance, "pid", "unknown")
    security_logger.warning(
        f"BUNDLE_DELETED: name={bundle_name} pid={bundle_pid} pk={instance.pk}"
    )
