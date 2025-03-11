from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# Create your models here.

class S3ResourceLocation(models.Model):
    """
    Maps between persistent identifiers (handles) and S3 storage locations.
    """
    # The handle/PID
    resource_pid = models.URLField(
        null=False,
        unique=True,
        help_text="PID/Handle that uniquely identifies the resource"
    )
    
    # S3 storage information
    s3_bucket = models.CharField(
        max_length=255,
        null=False,
        help_text="S3 bucket name where the resource is stored"
    )
    s3_key = models.CharField(
        max_length=1024,
        null=False,
        help_text="S3 object key for the resource"
    )
    
    # Optional metadata
    content_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Content type of the resource"
    )
    size_bytes = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Size of the resource in bytes"
    )
    
    # Generic foreign key to link to any resource model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the resource"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the resource object"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    class Meta:
        verbose_name = "S3 Resource Location"
        verbose_name_plural = "S3 Resource Locations"
        indexes = [
            models.Index(fields=['resource_pid']),
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"{self.resource_pid} -> s3://{self.s3_bucket}/{self.s3_key}"
    
    def get_s3_url(self):
        """Generate the S3 URL for this resource"""
        return f"s3://{self.s3_bucket}/{self.s3_key}"


class ACFLPermissions(models.Model):
    """
    Stores ACFL permission information for collections and bundles.
    """
    # Generic foreign key to link to Collection or Bundle
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the object (Collection or Bundle)"
    )
    object_id = models.PositiveIntegerField(
        help_text="ID of the object"
    )
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # S3 location of the ACFL file
    acfl_file_bucket = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="S3 bucket containing the ACFL file"
    )
    acfl_file_key = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="S3 key for the ACFL file"
    )
    
    # Parsed permissions data
    permissions_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Parsed ACFL permissions data"
    )
    
    # Tracking fields
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the permissions were last synced from S3"
    )
    
    class Meta:
        verbose_name = "ACFL Permissions"
        verbose_name_plural = "ACFL Permissions"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]
    
    def __str__(self):
        return f"ACFL Permissions for {self.content_object}"
