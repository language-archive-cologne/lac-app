from django.db import models
from lacos.blam.models.base_repository import Repository
from lacos.blam.models.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection_structural_info import CollectionStructuralInfo


class Collection(Repository):
    """
    Concrete implementation of Repository for collections.
    A collection is a curated set of bundles that form a meaningful unit.
    """
    general_info = models.ForeignKey(
        CollectionGeneralInfo,
        on_delete=models.CASCADE,
        related_name='collections'
    )
    publication_info = models.ForeignKey(
        CollectionPublicationInfo,
        on_delete=models.CASCADE,
        related_name='collections'
    )
    administrative_info = models.ForeignKey(
        CollectionAdministrativeInfo,
        on_delete=models.CASCADE,
        related_name='collections'
    )
    structural_info = models.ForeignKey(
        CollectionStructuralInfo,
        on_delete=models.CASCADE,
        related_name='collections'
    )
    # Note: project_info is inherited from Repository and uses the concrete ProjectInfo model

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"

    def __str__(self):
        return self.general_info.display_title if hasattr(self, 'general_info') else f"Collection {self.id}"
