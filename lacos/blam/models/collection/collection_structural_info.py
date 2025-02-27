from django.db import models
from lacos.blam.models.base_structural_info import AdditionalMetadataFile, StructuralInfo
from base_indentifiers import IdentifierTypeChoices


class CollectionStructuralInfo(StructuralInfo):
    """
    Concrete implementation of StructuralInfo for collections
    """

    additional_metadata_files = models.ManyToManyField('CollectionAdditionalMetadataFile', blank=True)
    collection_topics = models.ManyToManyField('CollectionTopic', blank=True)
    collection_members = models.ManyToManyField('CollectionMembers', blank=True)

    class Meta:
        verbose_name = "Collection Structural Info"
        verbose_name_plural = "Collection Structural Info"

class CollectionAdditionalMetadataFile(AdditionalMetadataFile):
    """
    Concrete model for additional metadata files associated with a collection.
    """
    class Meta:
        verbose_name = "Collection Additional Metadata File"
        verbose_name_plural = "Collection Additional Metadata Files"


class CollectionTopic(models.Model):
    """
    A term that occurs as a BundleKeyword in a subset of bundles and defines 
    a meaningful subsection of the collection.
    
    """
    name = models.CharField(
        max_length=255,
        null=False,
        help_text="Topic term that defines a meaningful subsection of the collection"
    )
    
    class Meta:
        verbose_name = "Collection Topic"
        verbose_name_plural = "Collection Topics"

    def __str__(self):
        return self.name


class CollectionTopics(models.Model):
    """
    Model for managing topics associated with a collection.
    """
    collection = models.ForeignKey(
        'Collection',
        on_delete=models.CASCADE,
        related_name='collection_topics',
        help_text="Collection associated with these topics"
    )
    topics = models.ManyToManyField(
        'CollectionTopic',
        related_name='collections',
        help_text="Topics associated with the collection"
    )

    class Meta:
        verbose_name = "Collection Topics"
        verbose_name_plural = "Collection Topics"


class CollectionMembers(models.Model):
    """
    The CollectionMembers component contains elements referencing the bundles of the collection.
    """
    collection = models.OneToOneField(
        'Collection',
        on_delete=models.CASCADE,
        related_name='members',
        help_text="Collection that contains these members"
    )
    
    class Meta:
        verbose_name = "Collection Members"
        verbose_name_plural = "Collection Members"


class CollectionHasCollectionMember(models.Model):
    """
    References to a bundle contained in the collection. Based on the `hasCollectionMember` 
    relationship of the Fedora Relationship Ontology.

    """
    collection_members = models.ForeignKey(
        'CollectionMembers',
        on_delete=models.CASCADE,
        related_name='member_references',
        help_text="Collection members component this reference belongs to"
    )
    member_uri = models.URLField(
        null=False,
        help_text="URI reference to a bundle contained in the collection"
    )
    identifier_type = models.CharField(
        max_length=10,
        choices=IdentifierTypeChoices.choices,
        null=False,
        help_text="The identifier type used (DOI or Handle)"
    )
    order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional ordering of the member within the collection"
    )

    class Meta:
        verbose_name = "Collection Has Collection Member"
        verbose_name_plural = "Collection Has Collection Members"
        ordering = ['order']
