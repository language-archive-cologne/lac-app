from django.db import models
from lacos.blam.models.base_publication_info import PublicationInfo, Creator as BaseCreator, Contributor as BaseContributor


class CollectionPublicationInfoCreator(models.Model):
    """Through model for CollectionPublicationInfo <-> CollectionCreator M2M.

    Stores per-publication creator ordering independently, so shared
    CollectionCreator records don't corrupt each other's citation order.
    """
    collectionpublicationinfo = models.ForeignKey(
        'CollectionPublicationInfo',
        on_delete=models.CASCADE,
        db_column='collectionpublicationinfo_id',
    )
    collectioncreator = models.ForeignKey(
        'CollectionCreator',
        on_delete=models.CASCADE,
        db_column='collectioncreator_id',
    )
    order = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'blam_collectionpublicationinfo_creators'
        ordering = ['order']
        unique_together = [('collectionpublicationinfo', 'collectioncreator')]


class CollectionPublicationInfo(PublicationInfo):
    """
    Concrete implementation of PublicationInfo for Collections

    Extends the abstract PublicationInfo model with collection-specific fields
    and relationships.
    """
    collection = models.ForeignKey(
        'Collection',
        on_delete=models.CASCADE,
        related_name='publication_info'
    )
    creators = models.ManyToManyField(
        'CollectionCreator',
        blank=True,
        through='CollectionPublicationInfoCreator',
    )
    contributors = models.ManyToManyField('CollectionContributor', blank=True)
    
    class Meta:
        verbose_name = "Collection Publication Info"
        verbose_name_plural = "Collection Publication Info"


class CollectionCreator(BaseCreator):
    """
    Concrete implementation of Creator for Collections
    
    Represents individuals who created the collection.
    """
    class Meta:
        verbose_name = "Collection Creator"
        verbose_name_plural = "Collection Creators"


class CollectionContributor(BaseContributor):
    """
    Concrete implementation of Contributor for Collections
    
    Represents individuals who contributed to the collection in various roles.
    """
    contributor_display_name = models.CharField(max_length=255, null=False)
    class Meta:
        verbose_name = "Collection Contributor"
        verbose_name_plural = "Collection Contributors"
