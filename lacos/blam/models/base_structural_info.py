from django.db import models

class StructuralInfo(models.Model):
    """
    Abstract base model for structural information
    """
    additional_metadata_files = models.ManyToManyField('AdditionalMetadataFile', blank=True)
    
    class Meta:
        abstract = True

class AdditionalMetadataFile(models.Model):
    """
    Abstract model for additional metadata files associated with the resource.
    """
    file_name = models.CharField(
        max_length=255,
        null=False,
        help_text="Name of the metadata file"
    )
    file_pid = models.URLField(
        max_length=255,
        null=False,
        help_text="Persistent identifier URL for the metadata file"
    )
    mime_type = models.CharField(
        max_length=100,
        null=False,
        help_text="MIME type of the metadata file"
    )
    is_metadata_for = models.CharField(
        max_length=255,
        null=False,
        help_text="Identifier of the resource this metadata file describes"
    )
    file_description = models.TextField(
        null=True,
        blank=True,
        help_text="Description of the metadata file"
    )
    
    class Meta:
        abstract = True


