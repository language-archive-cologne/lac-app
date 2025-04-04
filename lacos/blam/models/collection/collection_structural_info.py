from django.db import models
from lacos.blam.models.base_structural_info import StructuralInfo, AdditionalMetadataFile


class CollectionStructuralInfo(StructuralInfo):
    """
    Concrete implementation of StructuralInfo for collections.
    Represents the structural information of a collection including its additional metadata files.


    """
    collection = models.ForeignKey(
        'Collection',
        on_delete=models.CASCADE,
        related_name='structural_info'
    )
    additional_metadata_files = models.ManyToManyField(
        'CollectionAdditionalMetadataFile',
        blank=True,
        help_text="Additional metadata files associated with this collection"
    )

    class Meta:
        verbose_name = "Collection Structural Info"
        verbose_name_plural = "Collection Structural Info"

    def __str__(self):
        return f"Collection Structural Info {self.id}"


class CollectionAdditionalMetadataFile(AdditionalMetadataFile):


    class Meta:
        verbose_name = "Collection Additional Metadata File"
        verbose_name_plural = "Collection Additional Metadata Files"

    def __str__(self):
        return f"{self.file_name} ({self.is_metadata_for})"
