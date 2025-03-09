from django.utils import timezone
from lacos.blam.models.base_model import BaseModel
from django.db import models

class MdLicense(BaseModel):
    """
    Abstract base model for CMDI License information.
    
    The CMDI License contains metadata about the license of the metadata document.
    
    Requirements:
    - Each metadata document must have a unique license
    """
    md_license = models.CharField(
        max_length=255,
        help_text="License of the metadata"
    )
    md_license_uri = models.URLField(
        help_text="URI of the license", unique=True
    )
    
    class Meta:
        abstract = True
        verbose_name = "Metadata License"
        verbose_name_plural = "Metadata Licenses"

    def __str__(self):
        return f"License: {self.md_license}"
