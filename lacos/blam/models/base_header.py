from django.utils import timezone
from lacos.blam.models.base_model import BaseModel
from django.db import models
class MdHeader(BaseModel):
    """
    Abstract base model for CMDI Header information.
    
    The CMDI Header contains metadata about the metadata document itself,
    such as who created it, when it was created, and identifiers for the
    metadata document.
    
    Requirements:
    - Each metadata document must have a unique self-link identifier
    """
    md_creator = models.CharField(
        max_length=255,
        help_text="Person or organization that created the metadata"
    )
    md_creation_date = models.DateField(
        default=timezone.now,
        help_text="Date when the metadata was created"
    )
    md_self_link = models.URLField(
        unique=True,
        help_text="Persistent identifier for this metadata document"
    )
    md_profile = models.URLField(
        help_text="URL of the metadata profile used"
    )
    
    class Meta:
        abstract = True
        verbose_name = "Metadata Header"
        verbose_name_plural = "Metadata Headers"

    def __str__(self):
        return f"Metadata by {self.md_creator} ({self.md_creation_date})"
