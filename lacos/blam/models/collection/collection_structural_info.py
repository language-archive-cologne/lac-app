from django.db import models
from lacos.blam.models.base_structural_info import AdditionalMetadataFile, StructuralInfo
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_repository import Bundle


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
    
    This model supports both direct references to existing bundles and identifier-based
    references for bundles that don't exist yet in the system.
    """
    collection_members = models.ForeignKey(
        'CollectionMembers',
        on_delete=models.CASCADE,
        related_name='member_references',
        help_text="Collection members component this reference belongs to"
    )
    
    # Direct reference to bundle when it exists
    bundle = models.ForeignKey(
        Bundle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collection_references',
        help_text="Direct reference to the bundle when it exists in the system"
    )
    
    # Identifier information for when bundle doesn't exist yet
    identifier = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        help_text="The identifier value (DOI or Handle) for the bundle"
    )
    identifier_type = models.CharField(
        max_length=10,
        choices=IdentifierTypeChoices.choices,
        null=False,
        blank=False,
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
        unique_together = [('identifier', 'identifier_type')]
        
    def resolve_bundle(self):
        """
        Attempts to resolve and link to the actual bundle if it exists in the system.
        If no bundle exists with this identifier, creates just the publication info
        with only the identifier information.
        Returns True if successful, False if there was an error.
        """
        if self.bundle is not None:
            return True
            
        try:
            # Try to find the bundle by its identifier
            from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
            
            # First, check if a bundle with this identifier already exists
            try:
                bundle = Bundle.objects.get(
                    publication_info__identifier=self.identifier,
                    publication_info__identifier_type=self.identifier_type
                )
                self.bundle = bundle
                self.save()
                return True
            except Bundle.DoesNotExist:
                # Check if publication info with this identifier exists
                try:
                    pub_info = BundlePublicationInfo.objects.get(
                        identifier=self.identifier,
                        identifier_type=self.identifier_type
                    )
                except BundlePublicationInfo.DoesNotExist:
                    # Create new publication info with the identifier
                    pub_info = BundlePublicationInfo.objects.create(
                        identifier=self.identifier,
                        identifier_type=self.identifier_type,
                        # Required fields from PublicationInfo
                        publication_year=0,  # Placeholder value
                        data_provider="Placeholder"  # Placeholder value
                    )
                
                # We don't create a bundle here, just the publication info
                return True
            
        except Exception as e:
            # Log the error
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error resolving bundle for {self.identifier_type} {self.identifier}: {str(e)}")
            return False
