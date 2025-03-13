from django.db import models
from lacos.blam.models.base_model import BaseModel       
from lacos.storage.models import S3ResourceLocation, ACFLPermissions

class Repository(BaseModel):
    """
    Abstract base model for repository information
    
    This class defines the common structure for repositories (Bundles, Collections, etc.)
    with relationships to various types of information. Concrete subclasses should
    override these fields with specific implementations.
    """

    base_header = models.ForeignKey(
        'MdHeader',
        on_delete=models.CASCADE,
        related_name='base_header'
    )
    base_license = models.ForeignKey(
        'MdLicense',
        on_delete=models.CASCADE,
        related_name='base_license'
    )
    general_info = models.ForeignKey(
        'GeneralInfo',
        on_delete=models.CASCADE,
        related_name='base_general'
    )
    publication_info = models.ForeignKey(
        'PublicationInfo',
        on_delete=models.CASCADE,
        related_name='base_publication'
    )
    project_info = models.ForeignKey(
        'ProjectInfo',
        on_delete=models.CASCADE,
        related_name='base_project'
    )
    administrative_info = models.ForeignKey(
        'AdministrativeInfo',
        on_delete=models.CASCADE,
        related_name='base_administrative'
    )
    structural_info = models.ForeignKey(
        'StructuralInfo',
        on_delete=models.CASCADE,
        related_name='base_structural'
    )

    
    class Meta:
        abstract = True

    def get_s3_location(self):
        """Get the S3 location for this repository"""
        try:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self)
            location = S3ResourceLocation.objects.get(
                content_type=ct,
                object_id=self.id
            )
            return location
        except S3ResourceLocation.DoesNotExist:
            return None

    def get_s3_url(self):
        """Get the S3 URL for this repository"""
        location = self.get_s3_location()
        if location:
            return location.get_s3_url()
        return None
        
    def get_presigned_url(self, expires_in=3600):
        """Generate a presigned URL for temporary access"""
        location = self.get_s3_location()
        if location:
            from lacos.storage.services import S3Service
            return S3Service.generate_presigned_url(
                location.s3_bucket,
                location.s3_key,
                expires_in=expires_in
            )
        return None

    def get_acfl_permissions(self):
        """Get the ACFL permissions for this repository"""
        try:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(self)
            permissions = ACFLPermissions.objects.get(
                content_type=ct,
                object_id=self.id
            )
            return permissions
        except ACFLPermissions.DoesNotExist:
            return None
            
    def refresh_acfl_permissions(self):
        """Refresh ACFL permissions from S3"""
        from lacos.storage.services import ACFLService
        return ACFLService.refresh_permissions(self)
        
    def check_permission(self, user, permission_type='read'):
        """Check if a user has permission on this repository"""
        from lacos.storage.services import ACFLService
        return ACFLService.check_permission(user, self, permission_type)

    def register_s3_location(self, bucket, key, pid_url=None):
        """Register S3 location for this repository"""
        from lacos.storage.services import S3Service
        return S3Service.register_s3_location(self, bucket, key, pid_url)
        
    def register_acfl_file(self, bucket, key):
        """Register ACFL file location for this repository"""
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(self)
        
        acfl, created = ACFLPermissions.objects.update_or_create(
            content_type=ct,
            object_id=self.id,
            defaults={
                'acfl_file_bucket': bucket,
                'acfl_file_key': key
            }
        )
        return acfl
