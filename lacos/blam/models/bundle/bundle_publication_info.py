from django.db import models
from lacos.blam.models.base_publication_info import PublicationInfo, Creator as BaseCreator, Contributor as BaseContributor


class BundlePublicationInfo(PublicationInfo):
    """
    Concrete implementation of PublicationInfo for Bundles
    
    Extends the abstract PublicationInfo model with bundle-specific fields
    and relationships.
    """

    creators = models.ManyToManyField('BundleCreator', blank=True)
    contributors = models.ManyToManyField('BundleContributor', blank=True)
    
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
    contributor_name = models.ForeignKey('BundleContributorName', on_delete=models.CASCADE, related_name='bundle_contributors')
    
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
