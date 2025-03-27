from django.db import models
from lacos.blam.models.base_repository import Repository
from lacos.blam.models.bundle.bundle_header import BundleHeader
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_administrative_info import BundleAdministrativeInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo


class Bundle(Repository):
    """
    Concrete implementation of Repository for bundles.
    A bundle is a coherent set of data and metadata files that form a meaningful unit.
    """
    base_header = models.ForeignKey(
        BundleHeader,
        on_delete=models.CASCADE,
        related_name='bundle_header_info'
    )
    general_info = models.ForeignKey(
        BundleGeneralInfo,
        on_delete=models.CASCADE,
        related_name='bundle_general_info'
    )
    publication_info = models.ForeignKey(
        BundlePublicationInfo,
        on_delete=models.CASCADE,
        related_name='bundle_publication_info'
    )

    administrative_info = models.ForeignKey(
        BundleAdministrativeInfo,
        on_delete=models.CASCADE,
        related_name='bundle_administrative_info'
    )
    structural_info = models.ForeignKey(
        BundleStructuralInfo,
        on_delete=models.CASCADE,
        related_name='bundle_structural_info'
    )

    class Meta:
        verbose_name = "Bundle"
        verbose_name_plural = "Bundles"

    def __str__(self):
        return self.general_info.display_title if hasattr(self, 'general_info') else f"Bundle {self.id}"
