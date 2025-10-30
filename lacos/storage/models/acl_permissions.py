from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from lacos.storage.constants import (
    ACL_LEVEL_EMBARGO,
    ACL_LEVEL_PRIVATE,
    ACL_LEVEL_PROTECTED,
    ACL_LEVEL_PUBLIC,
)


class ACLPermissions(models.Model):
    """
    Stores ACL permission information for collections and bundles.
    """

    ACCESS_LEVEL_CHOICES = [
        (ACL_LEVEL_EMBARGO, "Embargo"),
        (ACL_LEVEL_PRIVATE, "Private"),
        (ACL_LEVEL_PROTECTED, "Protected"),
        (ACL_LEVEL_PUBLIC, "Public"),
    ]

    # Generic foreign key to link to Collection or Bundle
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        help_text="Type of the object (Collection or Bundle)",
    )
    object_id = models.CharField(
        max_length=36,
        help_text="ID of the object",
    )
    content_object = GenericForeignKey("content_type", "object_id")

    # S3 location of the ACL file
    ACL_file_bucket = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="S3 bucket containing the ACL file",
    )
    ACL_file_key = models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="S3 key for the ACL file",
    )

    # Parsed permissions data
    permissions_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Parsed ACL permissions data",
    )

    # Derived summary fields
    access_level = models.CharField(
        max_length=20,
        choices=ACCESS_LEVEL_CHOICES,
        default=ACL_LEVEL_EMBARGO,
        help_text="Normalised access level inferred from the ACL entries",
    )
    read_agents = models.JSONField(
        null=True,
        blank=True,
        help_text="List of agent URIs or classes that have read access",
    )

    # Tracking fields
    last_synced = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the permissions were last synced from S3",
    )

    class Meta:
        verbose_name = "ACL Permissions"
        verbose_name_plural = "ACL Permissions"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"ACL Permissions for {self.content_object}"
