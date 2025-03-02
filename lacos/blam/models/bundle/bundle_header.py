from lacos.blam.models.base_header import MdHeader

class BundleHeader(MdHeader):
    """
    CMDI Header information for Bundle metadata.
    Contains metadata about the metadata document itself.
    """
    class Meta:
        verbose_name = "Bundle Header"
        verbose_name_plural = "Bundle Headers"
