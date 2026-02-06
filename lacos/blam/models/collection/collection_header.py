from django.db import models
from lacos.blam.models.base_header import MdHeader

class CollectionHeader(MdHeader):
    """
    CMDI Header information for Collection metadata.
    Contains metadata about the metadata document itself, plus
    collection-specific header information.
    """

    collection = models.ForeignKey(
        'Collection',
        on_delete=models.CASCADE,
        related_name='header'
    )
    md_collection_display_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Display name for the collection this metadata belongs to"
    )
    md_license = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Metadata document license (MDLicense value)",
    )
    md_license_uri = models.URLField(
        null=True,
        blank=True,
        help_text="Metadata document license URI (MDLicense URI)",
    )
    
    class Meta:
        verbose_name = "Collection Header"
        verbose_name_plural = "Collection Headers"
