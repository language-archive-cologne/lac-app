from django.db import models
from lacos.blam.models.base_structural_info import AdditionalMetadataFile, StructuralInfo
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_repository import Bundle
from blam_schemas.collection.blam_collection_repository_v1_0 import CollectionHasCollectionMemberIdentifierType


class CollectionStructuralInfo(StructuralInfo):
    """
    Concrete implementation of StructuralInfo for collections.
    Represents the structural information of a collection including its members and additional metadata files.
    """
    collection = models.OneToOneField(
        'Collection',
        on_delete=models.CASCADE,
        related_name='structural_info',
        null=True,
        help_text="The collection this structural info belongs to"
    )
    additional_metadata_files = models.ManyToManyField(
        'CollectionAdditionalMetadataFile',
        blank=True,
        help_text="Additional metadata files associated with this collection"
    )
    members = models.ManyToManyField(
        'CollectionHasCollectionMember',
        related_name='parent_collections',
        blank=True,
        help_text="Bundles that are members of this collection"
    )

    class Meta:
        verbose_name = "Collection Structural Info"
        verbose_name_plural = "Collection Structural Info"

    def __str__(self):
        return f"Structural Info for {self.collection}" if self.collection else "Unlinked Structural Info"


class CollectionAdditionalMetadataFile(models.Model):
    """
    Model for additional metadata files associated with a collection.
    """
    file_name = models.CharField(
        max_length=255,
        help_text="Name of the metadata file"
    )
    file_pid = models.CharField(
        max_length=255,
        help_text="Persistent identifier for the file"
    )
    mime_type = models.CharField(
        max_length=100,
        help_text="MIME type of the file"
    )
    is_metadata_for = models.CharField(
        max_length=50,
        help_text="Type of resource this metadata is for (e.g., collection, bundle)"
    )
    file_description = models.TextField(
        null=True,
        blank=True,
        help_text="Description of the metadata file"
    )
    structural_info = models.ForeignKey(
        CollectionStructuralInfo,
        on_delete=models.CASCADE,
        related_name='additional_metadata_files',
        help_text="The structural info this metadata file belongs to"
    )

    class Meta:
        verbose_name = "Collection Additional Metadata File"
        verbose_name_plural = "Collection Additional Metadata Files"

    def __str__(self):
        return f"{self.file_name} ({self.is_metadata_for})"


class CollectionHasCollectionMember(models.Model):
    """
    References to a bundle contained in the collection. Based on the `hasCollectionMember` 
    relationship of the Fedora Relationship Ontology.
    
    This model supports both direct references to existing bundles and identifier-based
    references for bundles that don't exist yet in the system.
    """
    bundle = models.ForeignKey(
        'bundle.Bundle',
        on_delete=models.CASCADE,
        related_name='collection_memberships',
        null=True,
        blank=True,
        help_text="The bundle if it exists in the system"
    )
    identifier = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Identifier for the bundle if not in the system"
    )
    identifier_type = models.CharField(
        max_length=50,
        choices=[(t.value, t.value) for t in CollectionHasCollectionMemberIdentifierType],
        help_text="Type of identifier used"
    )
    order = models.IntegerField(
        default=0,
        help_text="Order of the member in the collection"
    )

    class Meta:
        verbose_name = "Collection Member"
        verbose_name_plural = "Collection Members"
        ordering = ['order']

    def __str__(self):
        if self.bundle:
            return f"Bundle {self.bundle.id} in collection"
        return f"External bundle {self.identifier} ({self.identifier_type})"

    def resolve_bundle(self):
        """
        Attempt to find or create publication info based on the identifier and identifier type.
        """
        if not self.identifier or not self.identifier_type:
            return None

        # Try to find existing bundle
        if self.identifier_type == CollectionHasCollectionMemberIdentifierType.HANDLE.value:
            try:
                from lacos.blam.models.bundle.bundle import Bundle
                return Bundle.objects.get(handle=self.identifier)
            except Bundle.DoesNotExist:
                pass
        elif self.identifier_type == CollectionHasCollectionMemberIdentifierType.DOI.value:
            try:
                from lacos.blam.models.bundle.bundle import Bundle
                return Bundle.objects.get(doi=self.identifier)
            except Bundle.DoesNotExist:
                pass

        return None
