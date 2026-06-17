from django.db import models
from lacos.blam.models.base_model import BaseModel
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


class CollectionMember(BaseModel):
    """A bundle declared as a member of a collection via ``CollectionHasCollectionMember``.

    This records the *declared* membership straight from the collection's BLAM
    metadata, independent of whether the bundle's content has been imported into
    the active archive. The bundle-side ``BundleStructuralInfo.is_member_of_collection``
    relation only exists for bundles whose content is present, so this model is the
    authoritative source for members that are referenced but absent from the active
    store.
    """
    structural_info = models.ForeignKey(
        'CollectionStructuralInfo',
        on_delete=models.CASCADE,
        related_name='members',
    )
    identifier_value = models.CharField(
        max_length=255,
        help_text="Declared member identifier (e.g. a handle or DOI).",
    )
    identifier_type = models.CharField(
        max_length=20,
        blank=True,
        help_text="Identifier type as declared in the BLAM (e.g. Handle, DOI).",
    )

    class Meta:
        verbose_name = "Collection Member"
        verbose_name_plural = "Collection Members"
        constraints = [
            models.UniqueConstraint(
                fields=['structural_info', 'identifier_value'],
                name='unique_collection_member_identifier',
            ),
        ]

    def __str__(self):
        return f"{self.identifier_value} ({self.identifier_type or 'unknown'})"
