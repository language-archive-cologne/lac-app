from django.db import models
from lacos.blam.models.base_publication_info import PublicationInfo, Creator as BaseCreator, Contributor as BaseContributor


class BundlePublicationInfo(PublicationInfo):
    """
    Concrete implementation of PublicationInfo for Bundles
    
    Extends the abstract PublicationInfo model with bundle-specific fields
    and relationships.
    """

    bundle = models.ForeignKey(
        'Bundle',
        on_delete=models.CASCADE,
        related_name='publication_info'
    )
    creators = models.ManyToManyField('BundleCreator', blank=True)
    contributors = models.ManyToManyField('BundleContributor', blank=True)
    
    # Add identifier fields with not-null constraints
    identifier = models.CharField(max_length=255, null=False, blank=False)
    identifier_type = models.CharField(max_length=10, null=False, blank=False)
    
    class Meta:
        verbose_name = "Bundle Publication Info"
        verbose_name_plural = "Bundle Publication Info"


class BundleCreator(BaseCreator):
    """
    Concrete implementation of Creator for Bundles
    
    Represents individuals who created the bundle.
    """
    class Meta:
        verbose_name = "Bundle Creator"
        verbose_name_plural = "Bundle Creators"


class BundleContributor(BaseContributor):
    """
    Concrete implementation of Contributor for Bundles
    
    Represents individuals who contributed to the bundle in various roles.
    """
    contributor_name = models.ForeignKey('BundleContributorName', on_delete=models.CASCADE, related_name='contributors')
    
    class Meta:
        verbose_name = "Bundle Contributor"
        verbose_name_plural = "Bundle Contributors"


class BundleContributorName(models.Model):
    """
        ContributorName for Bundles
    """
    contributor_family_name = models.CharField(max_length=255, null=False)
    contributor_given_name = models.CharField(max_length=255, null=False)

    class Meta:
        verbose_name = "Bundle Contributor Name"
        verbose_name_plural = "Bundle Contributor Names"

    def __str__(self) -> str:
        return f"{self.contributor_family_name}, {self.contributor_given_name}"
