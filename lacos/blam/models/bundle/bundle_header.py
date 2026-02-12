from lacos.blam.models.base_header import MdHeader
from django.db import models
class BundleHeader(MdHeader):
    """
    CMDI Header information for Bundle metadata.
    Contains metadata about the metadata document itself.
    """
    bundle = models.ForeignKey(
        'Bundle',
        on_delete=models.CASCADE,
        related_name='header'
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
        verbose_name = "Bundle Header"
        verbose_name_plural = "Bundle Headers"
