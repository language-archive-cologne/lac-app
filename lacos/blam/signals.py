import logging
from django.db.models.signals import pre_delete
from django.dispatch import receiver
# Import the necessary models
from .models.bundle.bundle_structural_info import BundleStructuralInfo, MediaResource, WrittenResource, OtherResource 
from .models.bundle.bundle_repository import Bundle
from .models.collection.collection_repository import Collection
from lacos.storage.models import S3ResourceLocation
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger(__name__)

@receiver(pre_delete, sender=Collection)
def delete_collection_components(sender, instance, **kwargs):
    """
    Signal handler to delete all associated components when a Collection is deleted.
    
    This is necessary because the relationships are defined in the direction that doesn't 
    support proper CASCADE deletion (Collection has ForeignKey to components, not the other way around).
    
    Without this signal, the Collection components (header, info, etc.) would
    remain in the database even after the Collection is deleted.
    """
    try:
        # instance is the Collection object being deleted
        logger.info(f"PRE_DELETE signal: Processing deletion of components for Collection PK={instance.pk}")
        
        # Get all components before they become inaccessible
        try:
            base_header = getattr(instance, 'base_header', None)
            general_info = getattr(instance, 'general_info', None)
            publication_info = getattr(instance, 'publication_info', None)
            administrative_info = getattr(instance, 'administrative_info', None)
            structural_info = getattr(instance, 'structural_info', None)
            project_info = getattr(instance, 'project_info', None)
        except Exception as e:
            logger.warning(f"Could not access all components for Collection PK={instance.pk}: {e}")
            base_header = general_info = publication_info = administrative_info = structural_info = project_info = None
        
        # Delete each component if it exists
        if base_header:
            logger.info(f"Deleting CollectionHeader PK={base_header.pk} for Collection PK={instance.pk}")
            base_header.delete()
            
        if general_info:
            logger.info(f"Deleting CollectionGeneralInfo PK={general_info.pk} for Collection PK={instance.pk}")
            general_info.delete()
            
        if publication_info:
            logger.info(f"Deleting CollectionPublicationInfo PK={publication_info.pk} for Collection PK={instance.pk}")
            publication_info.delete()
            
        if administrative_info:
            logger.info(f"Deleting CollectionAdministrativeInfo PK={administrative_info.pk} for Collection PK={instance.pk}")
            administrative_info.delete()
            
        if structural_info:
            logger.info(f"Deleting CollectionStructuralInfo PK={structural_info.pk} for Collection PK={instance.pk}")
            structural_info.delete()
            
        # Project info might be shared between collections, so only delete if not used by others
        if project_info:
            # Check if this project_info is referenced by other collections
            if not project_info.collection_project_info.exclude(pk=instance.pk).exists():
                logger.info(f"Deleting ProjectInfo PK={project_info.pk} for Collection PK={instance.pk}")
                project_info.delete()
            else:
                logger.info(f"ProjectInfo PK={project_info.pk} is used by other collections, not deleting")
        
        logger.info(f"Finished deleting components for Collection PK={instance.pk}")

    except Exception as e:
        logger.error(f"Error in pre_delete signal for Collection PK={instance.pk}: {e}", exc_info=True)

@receiver(pre_delete, sender=Bundle)
def delete_associated_structural_info(sender, instance, **kwargs):
    """
    Signal handler to delete all associated components when a Bundle is deleted.
    
    This is necessary because the relationships are defined in the direction that doesn't 
    support proper CASCADE deletion (Bundle has ForeignKey to components, not the other way around).
    
    Without this signal, the Bundle components (header, general_info, etc.) would
    remain in the database even after the Bundle is deleted.
    """
    try:
        # instance is the Bundle object being deleted
        logger.info(f"PRE_DELETE signal: Processing deletion of components for Bundle PK={instance.pk}")
        
        # Get all components before they become inaccessible
        try:
            base_header = getattr(instance, 'base_header', None)
            general_info = getattr(instance, 'general_info', None)
            publication_info = getattr(instance, 'publication_info', None)
            administrative_info = getattr(instance, 'administrative_info', None)
            structural_info = getattr(instance, 'structural_info', None)
        except Exception as e:
            logger.warning(f"Could not access all components for Bundle PK={instance.pk}: {e}")
            base_header = general_info = publication_info = administrative_info = structural_info = None
        
        # Delete each component if it exists
        if base_header:
            logger.info(f"Deleting BundleHeader PK={base_header.pk} for Bundle PK={instance.pk}")
            base_header.delete()
            
        if general_info:
            logger.info(f"Deleting BundleGeneralInfo PK={general_info.pk} for Bundle PK={instance.pk}")
            general_info.delete()
            
        if publication_info:
            logger.info(f"Deleting BundlePublicationInfo PK={publication_info.pk} for Bundle PK={instance.pk}")
            publication_info.delete()
            
        if administrative_info:
            logger.info(f"Deleting BundleAdministrativeInfo PK={administrative_info.pk} for Bundle PK={instance.pk}")
            administrative_info.delete()
        
        if structural_info:
            logger.info(f"PRE_DELETE signal: Deleting BundleStructuralInfo PK={structural_info.pk} for Bundle PK={instance.pk}")
            # This will trigger the delete_associated_resources signal for BundleStructuralInfo
            # which will delete the resources before the structural_info is deleted
            structural_info.delete()
            logger.info(f"Finished deleting BundleStructuralInfo for Bundle PK={instance.pk}")
        else:
            logger.warning(f"PRE_DELETE signal for Bundle PK={instance.pk}, but no associated BundleStructuralInfo found.")
        
        logger.info(f"Finished deleting components for Bundle PK={instance.pk}")

    except Exception as e:
        logger.error(f"Error in pre_delete signal for Bundle PK={instance.pk}: {e}", exc_info=True)

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
