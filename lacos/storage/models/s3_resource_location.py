from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

# Import the new models
from .upload_sessions import UploadSession
from .s3_file_objects import S3FileObject

class S3ResourceLocation(models.Model):
    """
    Maps between persistent identifiers (handles) and S3 storage locations.
    """
    # The handle/PID
    resource_pid = models.URLField(
        null=True,
        blank=True,
        unique=True,
        help_text="PID/Handle that uniquely identifies the resource (optional)"
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
    mime_type = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="MIME type of the resource (e.g., application/pdf)"
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
    object_id = models.CharField(
        max_length=36,  # Standard UUID length
        help_text="UUID or ID of the resource object"
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
        return f"{self.resource_pid} -> {self.s3_bucket}/{self.s3_key}"