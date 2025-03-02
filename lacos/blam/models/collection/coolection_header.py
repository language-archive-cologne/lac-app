from django.db import models
from lacos.blam.models.base_header import MdHeader

class CollectionHeader(MdHeader):
    """
    CMDI Header information for Collection metadata.
    Contains metadata about the metadata document itself, plus
    collection-specific header information.
    """
    md_collection_display_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Display name for the collection this metadata belongs to"
    )
    
    class Meta:
        verbose_name = "Collection Header"
        verbose_name_plural = "Collection Headers"