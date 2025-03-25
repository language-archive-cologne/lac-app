from django.db import models
from lacos.blam.models.base_repository import Repository
from lacos.blam.models.base_project_info import ProjectInfo
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
        related_name='bundles_header'
    )
    general_info = models.ForeignKey(
        BundleGeneralInfo,
        on_delete=models.CASCADE,
        related_name='bundles_general'
    )
    publication_info = models.ForeignKey(
        BundlePublicationInfo,
        on_delete=models.CASCADE,
        related_name='bundles_publication'
    )
    project_info = models.ForeignKey(
        ProjectInfo,
        on_delete=models.CASCADE,
        related_name='bundles_project'
    )

    administrative_info = models.ForeignKey(
        BundleAdministrativeInfo,
        on_delete=models.CASCADE,
        related_name='bundles_administrative'
    )
    structural_info = models.ForeignKey(
        BundleStructuralInfo,
        on_delete=models.CASCADE,
        related_name='bundles_structural'
    )

    class Meta:
        verbose_name = "Bundle"
        verbose_name_plural = "Bundles"

    def __str__(self):
        return self.general_info.display_title if hasattr(self, 'general_info') else f"Bundle {self.id}"
