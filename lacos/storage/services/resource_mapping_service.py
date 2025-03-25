from django.contrib.contenttypes.models import ContentType
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.models.acl_permissions import ACLPermissions
from .base_storage_service import BaseStorageService
import boto3
from django.conf import settings
from datetime import datetime, timedelta
import logging

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
        # Import here to avoid circular imports
        from lacos.blam.models.collection.collection_repository import Collection
        from lacos.blam.models.bundle.bundle_repository import Bundle
        
        if isinstance(obj, Collection):
            return f'collections/{obj.id}/'
        elif isinstance(obj, Bundle):
            collection = obj.structural_info.is_member_of_collection
            return f'collections/{collection.id}/bundles/{obj.id}/'
        else:
            # For resources, try to determine the path from relationships
            # Check for MediaResource, WrittenResource, or OtherResource
            if hasattr(obj, 'file_name') and hasattr(obj, 'file_pid'):
                # Try to find the parent bundle
                # This depends on how resources are related to bundles in your model
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
                    collection = bundle.structural_info.is_member_of_collection
                    return f'collections/{collection.id}/bundles/{bundle.id}/resources/{obj.file_name}'
        
        # Default case if we can't determine the path
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
