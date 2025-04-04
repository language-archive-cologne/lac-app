from django.db import models
from lacos.blam.models.base_administrative_info import (
    AdministrativeInfo,
    IdenticalResource,
    License,
    RightsHolder,
    RightsHolderIdentifier
)


class BundleIdenticalResource(IdenticalResource):
    """
    Concrete model for resources that are identical to a bundle.
    """
    class Meta:
        verbose_name = "Bundle Identical Resource"
        verbose_name_plural = "Bundle Identical Resources"


class BundleLicense(License):
    """
    Concrete model for license information under which a bundle is available.
    """
    class Meta:
        verbose_name = "Bundle License"
        verbose_name_plural = "Bundle Licenses"


class BundleRightsHolderIdentifier(RightsHolderIdentifier):
    """
    Concrete model for identifiers that uniquely identify bundle rights holders.
    """
    class Meta:
        verbose_name = "Bundle Rights Holder Identifier"
        verbose_name_plural = "Bundle Rights Holder Identifiers"


class BundleRightsHolder(RightsHolder):
    """
    Concrete model for information about the individual or institution
    owning or managing the rights in regard to a bundle.
    """
    rights_holder_identifiers = models.ManyToManyField(
        'BundleRightsHolderIdentifier',
        blank=True,
        related_name='rights_holders_identifiers',
        help_text="Identifiers for the rights holder"
    )

    class Meta:
        verbose_name = "Bundle Rights Holder"
        verbose_name_plural = "Bundle Rights Holders"


class BundleAdministrativeInfo(AdministrativeInfo):
    """
    Concrete model for administrative metadata for bundles that will be publicly communicated,
    especially in regard to metacatalogues and user interfaces.
    """


    bundle = models.ForeignKey(
        'Bundle',
        on_delete=models.CASCADE,
        related_name='administrative_info'
    )
    
    is_identical_to = models.ManyToManyField(
        'BundleIdenticalResource',
        blank=True,
        related_name='identical_resources',
        help_text="URIs that uniquely identify identical resources"
    )
    licenses = models.ManyToManyField(
        'BundleLicense',
        related_name='licenses',
        help_text="Licenses under which the resource is available"
    )
    rights_holders = models.ManyToManyField(
        'BundleRightsHolder',
        related_name='rights_holders',
        help_text="Individuals or institutions owning or managing the rights over the resource"
    )

    class Meta:
        verbose_name = "Bundle Administrative Info"
        verbose_name_plural = "Bundle Administrative Info"
