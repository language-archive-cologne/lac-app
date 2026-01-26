from django.db import models
from django.utils import timezone

from lacos.blam.models.base_model import UUIDTimestampModel
from .upload_sessions import UploadSession


class S3FileObject(UUIDTimestampModel):
    """Represents a file in S3"""
    session = models.ForeignKey(UploadSession, related_name='files', on_delete=models.CASCADE)
    bucket_name = models.CharField(max_length=255, blank=True)
    file_name = models.CharField(max_length=255)
    original_path = models.CharField(max_length=1024, blank=True)
    s3_key = models.CharField(max_length=1024)
    file_size_bytes = models.BigIntegerField(default=0)
    content_type = models.CharField(max_length=255, blank=True)
    upload_completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('uploading', 'Uploading'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('verified', 'Verified'),
        ],
        default='pending'
    )
    etag = models.CharField(max_length=255, blank=True)  # S3 ETag for verification
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "S3 File Object"
        verbose_name_plural = "S3 File Objects"
        indexes = [
            models.Index(fields=['session', 'status']),
            models.Index(fields=['s3_key']),
        ]

    def __str__(self):
        return f"{self.file_name} ({self.status})"
    
    def mark_completed(self, etag=None):
        """Mark the file as successfully uploaded"""
        self.status = 'completed'
        self.upload_completed_at = timezone.now()
        if etag:
            self.etag = etag
        self.save()
    
    def mark_failed(self, error_message):
        """Mark the file as failed with an error message"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()
    
    def mark_verified(self):
        """Mark the file as verified in S3"""
        self.status = 'verified'
        self.save() 