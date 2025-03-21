from django.db import models
from django.conf import settings
import uuid
from django.utils import timezone

class UploadSession(models.Model):
    """Represents a batch upload session"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # Use this instead of User directly
        on_delete=models.CASCADE
    )
    folder_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('initialized', 'Initialized'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='initialized'
    )
    total_files = models.IntegerField(default=0)
    total_size_bytes = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Upload Session"
        verbose_name_plural = "Upload Sessions"
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Upload {self.id} by {self.user.username} ({self.status})"
    
    def mark_completed(self):
        """Mark the session as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def get_progress(self):
        """Calculate upload progress percentage"""
        completed = self.files.filter(status='completed').count()
        if self.total_files == 0:
            return 0
        return (completed / self.total_files) * 100 