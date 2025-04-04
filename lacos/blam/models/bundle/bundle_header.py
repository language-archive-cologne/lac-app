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
    class Meta:
        verbose_name = "Bundle Header"
        verbose_name_plural = "Bundle Headers"
