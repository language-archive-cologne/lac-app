from django.contrib.contenttypes.models import ContentType
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.models.acl_permissions import ACLPermissions
from .base_storage_service import BaseStorageService
import boto3
from django.conf import settings
from datetime import datetime, timedelta
import logging
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources, MediaResource, WrittenResource, OtherResource
from uuid import UUID

logger = logging.getLogger(__name__)

class ResourceMappingService(BaseStorageService):
    """
    Service for managing the mapping between resources and their S3 storage locations.
    
    This service handles mapping between Django model objects (Collection, Bundle, Resources)
    and their corresponding locations in S3 storage.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ResourceMappingService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the ResourceMappingService with base storage configuration.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        logger.info("ResourceMappingService initialized")
        self.initialized = True
    
    def construct_s3_path(self, obj):
        """
        Construct the appropriate S3 path for an object based on its type.
        
        Args:
            obj: A Django model instance (Collection, Bundle, or Resource)
            
        Returns:
            str: The S3 path for the object, or None if the path can't be determined
        """
        # Import here placed at top level to avoid potential runtime issues
        
        if isinstance(obj, Collection):
            # Use UUID for path consistency
            return f'collections/{obj.id}/'
            
        elif isinstance(obj, Bundle):
            # Ensure structural_info and collection link exist
            if obj.structural_info.exists():
                si = obj.structural_info.first()
                if si.is_member_of_collection:
                    collection = si.is_member_of_collection
                    # Use UUIDs for path consistency
                    return f'collections/{collection.id}/bundles/{obj.id}/'
            
            logger.warning(f"Bundle {obj.id} is missing structural info or collection link. Cannot construct S3 path.")
            return None
                
        # --- Corrected Logic for Resource Types --- 
        elif isinstance(obj, (MediaResource, WrittenResource, OtherResource)):
            bundle = None
            try:
                # Get the BundleResources container(s) via the reverse M2M.
                bundle_resources_container = obj.bundleresources_set.first()
                
                # Debug logging
                logger.info(f"Resource type: {type(obj).__name__}, ID: {obj.id}")
                logger.info(f"BundleResources containers: {obj.bundleresources_set.count()}")
                if bundle_resources_container:
                    logger.info(f"First container ID: {bundle_resources_container.id}, bundle ID: {bundle_resources_container.bundle_id}")

                if bundle_resources_container:
                    # Directly access the bundle via the foreign key
                    bundle = bundle_resources_container.bundle
                    logger.info(f"Found bundle ID: {bundle.id if bundle else None}")
                    
                    # Get structural info if it exists
                    if bundle:
                        logger.info(f"Bundle has structural_info: {bundle.structural_info.count()}")
                        si = bundle.structural_info.first()
                        if si:
                            logger.info(f"StructInfo collection: {si.is_member_of_collection_id}")
                            collection = si.is_member_of_collection
                            if collection and hasattr(obj, 'file_name') and obj.file_name:
                                # Use UUIDs for path consistency
                                return f'collections/{collection.id}/bundles/{bundle.id}/resources/{obj.file_name}'

            except Exception as e: # Catch broader exceptions during traversal/query
                 # Handle cases where relations might not exist or query fails
                 logger.warning(f"Could not find related Bundle for resource {type(obj).__name__} (ID: {obj.id}). Check model relations: {e}", exc_info=False)
                 bundle = None # Ensure bundle is None if any step failed
                 
            # Only if relationships are correctly detected but somehow invalid, we'll reach this section
            if bundle and hasattr(obj, 'file_name') and obj.file_name:
                # Find collection through structural_info
                si = bundle.structural_info.first()
                if si and si.is_member_of_collection:
                    collection = si.is_member_of_collection
                    # Use UUIDs for path consistency
                    return f'collections/{collection.id}/bundles/{bundle.id}/resources/{obj.file_name}'
                
            # Log if bundle couldn't be determined for a resource type object
            logger.warning(f"Failed to determine valid Bundle/Collection path for resource {type(obj).__name__} (ID: {obj.id}).")
            return None
                 
        else:
            # Default case if object type is not recognized
            logger.warning(f"Cannot construct S3 path for unrecognized object type: {type(obj).__name__}")
            return None
    
    def get_s3_location(self, obj):
        """Get S3 location for any object (Collection, Bundle, or Resource)"""
        try:
            ct = ContentType.objects.get_for_model(obj)
            location = S3ResourceLocation.objects.get(
                content_type=ct,
                object_id=obj.id
            )
            return location
        except S3ResourceLocation.DoesNotExist:
            return None
    
    def resolve_pid_to_s3(self, pid_url):
        """Resolve a PID URL to an S3 location"""
        try:
            location = S3ResourceLocation.objects.get(resource_pid=pid_url)
            return location
        except S3ResourceLocation.DoesNotExist:
            return None
    
    def register_s3_location(self, obj, bucket, key=None, pid_url=None):
        """
        Register S3 location for an object
        
        Args:
            obj: The object to register (Collection, Bundle, or Resource)
            bucket: S3 bucket name
            key: S3 object key (if None, will be constructed from the object)
            pid_url: PID URL (if None, will try to use obj.file_pid)
            
        Returns:
            S3ResourceLocation: The created or updated location
        """
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(obj)
        
        # If no key provided, try to construct it
        if key is None:
            key = self.construct_s3_path(obj)
            if key is None:
                raise ValueError(f"Could not construct S3 path for {obj}. Please provide a key.")
        
        # If no PID URL provided but object has file_pid, use that
        if pid_url is None and hasattr(obj, 'file_pid'):
            pid_url = obj.file_pid
        
        # Create or update S3 location
        location, created = S3ResourceLocation.objects.update_or_create(
            content_type=ct,
            object_id=obj.id,
            defaults={
                'resource_pid': pid_url,
                's3_bucket': bucket,
                's3_key': key
            }
        )
        return location
    
    def generate_presigned_url(self, bucket, key, expires_in=3600):
        """Generate a presigned URL for temporary access"""
        url = self.presigned_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': key
            },
            ExpiresIn=expires_in
        )
        return url

    def get_resource_url(self, resource):
        """Get a presigned URL for a resource"""
        location = self.get_s3_location(resource)
        if not location:
            raise ValueError(f"No S3 location found for resource: {resource}")
        return self.generate_presigned_url(location.s3_bucket, location.s3_key)
    
    def get_resource_url_by_pid(self, pid):
        """Get a presigned URL for a resource by its PID"""
        location = self.resolve_pid_to_s3(pid)
        if not location:
            raise ValueError(f"No S3 location found for PID: {pid}")
        return self.generate_presigned_url(location.s3_bucket, location.s3_key)
        
    def batch_register_resources(self, resources, bucket, base_key):
        """Register multiple resources in a batch"""
        for resource in resources:
            # Extract the last part of the PID as a file name if no file_name is available
            if hasattr(resource, 'file_pid'):
                file_name = resource.file_pid.split('/')[-1]
                s3_key = f"{base_key}/{file_name}"
                self.register_s3_location(resource, bucket, s3_key)

    def map_collection_hierarchy(self, collection_id: UUID) -> int:
        """
        Map an entire collection hierarchy to S3 locations.
        
        Creates S3ResourceLocation entries for a collection, its bundles and resources.
        
        Args:
            collection_id: The collection UUID to map
            
        Returns:
            int: Total number of objects mapped
        """
        from lacos.blam.models.collection.collection_repository import Collection
        from lacos.blam.models.bundle.bundle_repository import Bundle
        from lacos.storage.services.file_discovery_service import FileDiscoveryService
        
        total_mapped = 0
        discovery_service = FileDiscoveryService()  # Needed for path formatting
        
        try:
            collection = Collection.objects.get(id=collection_id)
            
            # 1. Map the Collection object itself
            try:
                # Use FileDiscoveryService to get the expected S3 *prefix* (key) for the collection
                collection_key_prefix = discovery_service.form_collection_path(collection_id) + "/"  # Ensure trailing slash
                # Bucket usually comes from settings or service default
                bucket = discovery_service.production_bucket
                
                self.register_s3_location(collection, bucket, collection_key_prefix)
                logger.info(f"Mapped Collection {collection_id} to S3 location: {bucket}/{collection_key_prefix}")
                total_mapped += 1
            except Exception as e:
                logger.error(f"Failed to map Collection {collection_id} object: {e}", exc_info=True)
            
            # 2. Map associated Bundles and their Resources
            # Ensure bundle links have been resolved before running this
            if hasattr(collection, 'structural_info') and collection.structural_info:
                try:
                    # Use the reverse relationship from Collection to BundleStructuralInfo
                    linked_bundles = Bundle.objects.filter(
                        structural_info__is_member_of_collection=collection
                    ).distinct()
                    
                    logger.info(f"Found {linked_bundles.count()} linked bundles to map for collection {collection_id}.")
                except Exception as e:
                    logger.warning(f"Error querying linked bundles with standard relationship: {e}")
                    # If the above query fails, try a more direct approach
                    try:
                        # Get bundles via the bundle_collection reverse relationship
                        linked_bundles = Bundle.objects.filter(
                            structural_info__in=collection.bundle_collection.all()
                        ).distinct()
                        logger.info(f"Found {linked_bundles.count()} linked bundles using bundle_collection reverse relation")
                    except Exception as alt_e:
                        logger.error(f"Failed with alternative bundle lookup approach as well: {alt_e}")
                        linked_bundles = Bundle.objects.none()
                
                for bundle in linked_bundles:
                    try:
                        # Map the Bundle object
                        bundle_key_prefix = discovery_service.form_bundle_path(collection_id, bundle.id) + "/"  # Ensure trailing slash
                        self.register_s3_location(bundle, bucket, bundle_key_prefix)
                        logger.info(f"Mapped Bundle {bundle.id} to S3 location: {bucket}/{bundle_key_prefix}")
                        total_mapped += 1
                        
                        # 3. Map Resources within the Bundle
                        try:
                            resource_pattern = discovery_service.get_resource_path_pattern()
                            prefix_pattern = resource_pattern.rsplit('{resource_filename}', 1)[0]
                            resources_base_key = prefix_pattern.format(collection_id=collection_id, bundle_id=bundle.id)
                        except Exception as format_e:
                            logger.error(f"Could not format resource base key for bundle {bundle.id}: {format_e}")
                            continue  # Skip resource mapping for this bundle
                        
                        resource_count = 0
                        # Check if bundle has structural_info with resources
                        if hasattr(bundle, 'structural_info') and bundle.structural_info and hasattr(bundle.structural_info, 'resources') and bundle.structural_info.resources:
                            bundle_resources = bundle.structural_info.resources
                            
                            # Map media resources
                            if hasattr(bundle_resources, 'bundle_media_resources'):
                                for media_resource in bundle_resources.bundle_media_resources.all():
                                    if hasattr(media_resource, 'file_name') and media_resource.file_name:
                                        try:
                                            resource_s3_key = f"{resources_base_key}{media_resource.file_name}"
                                            self.register_s3_location(media_resource, bucket, resource_s3_key)
                                            resource_count += 1
                                            total_mapped += 1
                                        except Exception as res_map_e:
                                            logger.error(f"Failed to map media resource {getattr(media_resource, 'id', 'N/A')} (name: {media_resource.file_name}) for bundle {bundle.id}: {res_map_e}", exc_info=True)
                            
                            # Map written resources
                            if hasattr(bundle_resources, 'bundle_written_resources'):
                                for written_resource in bundle_resources.bundle_written_resources.all():
                                    if hasattr(written_resource, 'file_name') and written_resource.file_name:
                                        try:
                                            resource_s3_key = f"{resources_base_key}{written_resource.file_name}"
                                            self.register_s3_location(written_resource, bucket, resource_s3_key)
                                            resource_count += 1
                                            total_mapped += 1
                                        except Exception as res_map_e:
                                            logger.error(f"Failed to map written resource {getattr(written_resource, 'id', 'N/A')} (name: {written_resource.file_name}) for bundle {bundle.id}: {res_map_e}", exc_info=True)
                            
                            # Map other resources
                            if hasattr(bundle_resources, 'bundle_other_resources'):
                                for other_resource in bundle_resources.bundle_other_resources.all():
                                    if hasattr(other_resource, 'file_name') and other_resource.file_name:
                                        try:
                                            resource_s3_key = f"{resources_base_key}{other_resource.file_name}"
                                            self.register_s3_location(other_resource, bucket, resource_s3_key)
                                            resource_count += 1
                                            total_mapped += 1
                                        except Exception as res_map_e:
                                            logger.error(f"Failed to map other resource {getattr(other_resource, 'id', 'N/A')} (name: {other_resource.file_name}) for bundle {bundle.id}: {res_map_e}", exc_info=True)
                        
                        # For backwards compatibility, also try the old incorrect path
                        # Iterate through different resource types linked to the bundle
                        resource_relations = ['bundle_media_resources', 'bundle_written_resources', 'bundle_other_resources']
                        for relation_name in resource_relations:
                            if hasattr(bundle, relation_name):
                                related_manager = getattr(bundle, relation_name)
                                if hasattr(related_manager, 'all'):
                                    for bundle_resource_link in related_manager.all():
                                        # Get the actual resource instance (MediaResource, WrittenResource...)
                                        resource = None
                                        if hasattr(bundle_resource_link, 'media_resource'):
                                            resource = bundle_resource_link.media_resource
                                        elif hasattr(bundle_resource_link, 'written_resource'):
                                            resource = bundle_resource_link.written_resource
                                        elif hasattr(bundle_resource_link, 'other_resource'):
                                            resource = bundle_resource_link.other_resource
                                        
                                        if resource and hasattr(resource, 'file_name'):
                                            try:
                                                # Construct full S3 key for the resource
                                                resource_s3_key = f"{resources_base_key}{resource.file_name}"
                                                self.register_s3_location(resource, bucket, resource_s3_key)
                                                resource_count += 1
                                                total_mapped += 1
                                            except Exception as res_map_e:
                                                logger.error(f"Failed to map resource {getattr(resource, 'id', 'N/A')} (name: {resource.file_name}) for bundle {bundle.id}: {res_map_e}", exc_info=True)
                                        else:
                                            logger.warning(f"Could not map resource linked via {relation_name} for bundle {bundle.id}: Missing resource object or file_name.")
                        
                        logger.info(f"Mapped {resource_count} resources for Bundle {bundle.id}")
                    except Exception as bundle_map_e:
                        logger.error(f"Failed to map Bundle {bundle.id} or its resources: {bundle_map_e}", exc_info=True)
        
        except Collection.DoesNotExist:
            logger.error(f"Collection {collection_id} not found for resource mapping.")
            return 0
        except Exception as e:
            logger.error(f"Unexpected error mapping resources for collection {collection_id}: {e}", exc_info=True)
            return total_mapped
        
        return total_mapped  # Return count of mapped objects


# For backwards compatibility, create an alias
S3Service = ResourceMappingService


class ACFLService:
    @staticmethod
    def get_permissions(obj):
        """Get ACFL permissions for any object (Collection or Bundle)"""
        try:
            ct = ContentType.objects.get_for_model(obj)
            permissions = ACLPermissions.objects.get(
                content_type=ct,
                object_id=obj.id
            )
            return permissions
        except ACLPermissions.DoesNotExist:
            return None
    
    @staticmethod
    def create_permissions(obj, bucket, key, permissions_data=None):
        """Create ACFL permissions for an object"""
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(obj)
        
        # Create permissions
        permissions, created = ACLPermissions.objects.update_or_create(
            content_type=ct,
            object_id=obj.id,
            defaults={
                'ACL_file_bucket': bucket,
                'ACL_file_key': key,
                'permissions_data': permissions_data,
                'last_synced': datetime.now() if permissions_data else None
            }
        )
        return permissions
    
    @staticmethod
    def check_permission(user, obj, permission_type='read'):
        """
        Check if user has permission on an object
        
        Args:
            user: Django user
            obj: Collection, Bundle, or Resource instance
            permission_type: Type of permission to check
            
        Returns:
            bool: Whether user has permission
        """
        # First check object-specific permissions
        permissions = ACFLService.get_permissions(obj)
        if permissions and permissions.permissions_data:
            has_permission = ACFLService._check_acfl_permission(
                user, 
                permissions.permissions_data, 
                permission_type
            )
            if has_permission is not None:  # If explicitly granted or denied
                return has_permission
        
        # If no explicit permission or inheritance is enabled, check parent
        # Import here to avoid circular imports
        from lacos.blam.models.bundle.bundle_repository import Bundle
        
        # For bundles, check collection permissions
        if isinstance(obj, Bundle) and hasattr(obj, 'structural_info') and hasattr(obj.structural_info, 'is_member_of_collection'):
            collection = obj.structural_info.is_member_of_collection
            return ACFLService.check_permission(user, collection, permission_type)
        
        # For resources, check bundle permissions
        # This depends on how resources are related to bundles in your model
        if hasattr(obj, 'file_name') and hasattr(obj, 'file_pid'):
            bundle = None
            
            # Check if the resource has a direct reference to a bundle
            if hasattr(obj, 'bundle'):
                bundle = obj.bundle
            # Check if the resource is part of bundle_media_resources
            elif hasattr(obj, 'mediaresource') and hasattr(obj.mediaresource, 'bundle_media_resources'):
                for bundle_resources in obj.mediaresource.bundle_media_resources.all():
                    bundle = bundle_resources.bundle
                    break
            # Check if the resource is part of bundle_written_resources
            elif hasattr(obj, 'writtenresource') and hasattr(obj.writtenresource, 'bundle_written_resources'):
                for bundle_resources in obj.writtenresource.bundle_written_resources.all():
                    bundle = bundle_resources.bundle
                    break
            # Check if the resource is part of bundle_other_resources
            elif hasattr(obj, 'otherresource') and hasattr(obj.otherresource, 'bundle_other_resources'):
                for bundle_resources in obj.otherresource.bundle_other_resources.all():
                    bundle = bundle_resources.bundle
                    break
            
            if bundle:
                return ACFLService.check_permission(user, bundle, permission_type)
        
        # Default deny if no permissions found and no parent to check
        return False
    
    @staticmethod
    def _check_acfl_permission(user, acfl_data, permission_type):
        """
        Check if user has permission according to ACFL data
        
        This is a placeholder - implement based on your ACFL structure
        """
        # Example implementation - adjust to your ACFL structure
        if 'permissions' not in acfl_data:
            return None
        
        for perm in acfl_data['permissions']:
            if perm.get('type') == permission_type:
                # Check if user is in allowed users
                if 'users' in perm and user.username in perm['users']:
                    return True
                
                # Check if user is in allowed groups
                if 'groups' in perm:
                    user_groups = set(user.groups.values_list('name', flat=True))
                    if any(group in user_groups for group in perm['groups']):
                        return True
        
        return False
    
    @staticmethod
    def refresh_permissions(obj):
        """Refresh ACFL permissions from S3"""
        permissions = ACFLService.get_permissions(obj)
        if not permissions:
            return None
        
        # Get the ACFL file from S3
        resource_mapping_service = ResourceMappingService()
        s3_client = resource_mapping_service.s3_client
        
        try:
            response = s3_client.get_object(
                Bucket=permissions.ACL_file_bucket,
                Key=permissions.ACL_file_key
            )
            acfl_data = response['Body'].read().decode('utf-8')
            
            # Parse the ACFL data (assuming JSON format)
            import json
            permissions_data = json.loads(acfl_data)
            
            # Update the permissions
            permissions.permissions_data = permissions_data
            permissions.last_synced = datetime.now()
            permissions.save()
            
            return permissions
        except Exception as e:
            # Log the error
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error refreshing ACFL permissions: {e}")
            return None
