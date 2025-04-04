from django.db import models
from lacos.blam.models.base_administrative_info import (
    AdministrativeInfo,
    IdenticalResource,
    License,
    RightsHolder,
    RightsHolderIdentifier
)


class CollectionIdenticalResource(IdenticalResource):
    """
    Concrete model for resources that are identical to a collection.
    """
    class Meta:
        verbose_name = "Collection Identical Resource"
        verbose_name_plural = "Collection Identical Resources"


class CollectionLicense(License):
    """
    Concrete model for license information under which a collection is available.
    """
    class Meta:
        verbose_name = "Collection License"
        verbose_name_plural = "Collection Licenses"


class CollectionRightsHolderIdentifier(RightsHolderIdentifier):
    """
    Concrete model for identifiers that uniquely identify collection rights holders.
    """
    class Meta:
        verbose_name = "Collection Rights Holder Identifier"
        verbose_name_plural = "Collection Rights Holder Identifiers"


class CollectionRightsHolder(RightsHolder):
    """
    Concrete model for information about the individual or institution
    owning or managing the rights in regard to a collection.
    """
    rights_holder_identifiers = models.ManyToManyField(
        'CollectionRightsHolderIdentifier',
        blank=True,
        related_name='rights_holders_identifiers',
        help_text="Identifiers for the rights holder"
    )

    class Meta:
        verbose_name = "Collection Rights Holder"
        verbose_name_plural = "Collection Rights Holders"


class CollectionAdministrativeInfo(AdministrativeInfo):
    """
    Concrete model for administrative metadata for collections that will be publicly communicated,
    especially in regard to metacatalogues and user interfaces.
    """

    collection = models.ForeignKey(
        'Collection',
        on_delete=models.CASCADE,
        related_name='administrative_info'
    )
    
    is_identical_to = models.ManyToManyField(
        'CollectionIdenticalResource',
        blank=True,
        related_name='identical_resources',
        help_text="URIs that uniquely identify identical resources"
    )
    licenses = models.ManyToManyField(
        'CollectionLicense',
        related_name='licenses',
        help_text="Licenses under which the resource is available"
    )
    rights_holders = models.ManyToManyField(
        'CollectionRightsHolder',
        related_name='rights_holders',
        help_text="Individuals or institutions owning or managing the rights over the resource"
    )

    class Meta:
        verbose_name = "Collection Administrative Info"
        verbose_name_plural = "Collection Administrative Info"
