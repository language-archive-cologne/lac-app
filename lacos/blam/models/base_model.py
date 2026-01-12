from uuid_utils import uuid7
from django.db import models
from django.conf import settings


class UUIDTimestampModel(models.Model):
    """Base abstract model with UUID primary key and timestamps"""
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDTimestampModel):
    """Base abstract model with UUID primary key, timestamps, and audit fields"""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='%(class)s_created',
        editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='%(class)s_updated',
        editable=False,
    )

    class Meta:
        abstract = True