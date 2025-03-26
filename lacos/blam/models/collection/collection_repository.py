from django.db import models
from lacos.blam.models.base_repository import Repository
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from lacos.blam.models.collection.collection_publication_info import CollectionPublicationInfo
from lacos.blam.models.collection.collection_administrative_info import CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
from lacos.blam.models.base_project_info import ProjectInfo


class Collection(Repository):
    """
    Concrete implementation of Repository for collections.
    A collection is a curated set of bundles that form a meaningful unit.
    """

    base_header = models.ForeignKey(
        CollectionHeader,
        on_delete=models.CASCADE,
        related_name='collections_header'
    )
    general_info = models.ForeignKey(
        CollectionGeneralInfo,
        on_delete=models.CASCADE,
        related_name='collections_general'
    )
    publication_info = models.ForeignKey(
        CollectionPublicationInfo,
        on_delete=models.CASCADE,
        related_name='collections_publication'
    )
    project_info = models.ForeignKey(
        ProjectInfo,
        on_delete=models.CASCADE,
        related_name='collections_project'
    )
    administrative_info = models.ForeignKey(
        CollectionAdministrativeInfo,
        on_delete=models.CASCADE,
        related_name='collections_administrative'
    )
    structural_info = models.ForeignKey(
        CollectionStructuralInfo,
        on_delete=models.CASCADE,
        related_name='collections_structural',
        null=True,  # Allow null temporarily during creation
        help_text="Structural information about the collection"
    )

    class Meta:
        verbose_name = "Collection"
        verbose_name_plural = "Collections"

    def __str__(self):
        return self.general_info.display_title if hasattr(self, 'general_info') else f"Collection {self.id}"
