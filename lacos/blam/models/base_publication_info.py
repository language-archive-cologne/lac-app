from django.db import models
from base_indentifiers import PersonIdentifierTypeChoices


class PublicationInfo(models.Model):
    """
    Abstract model for publication information
    
    Common fields for both BundlePublicationInfo and CollectionPublicationInfo.
    Contains metadata about the publication process including year and data provider.
    """
    publication_year = models.IntegerField(null=False)
    data_provider = models.CharField(max_length=255, null=False)
    creators = models.ManyToManyField('Creator', blank=True, related_name='+')
    contributors = models.ManyToManyField('Contributor', blank=True, related_name='+')
    
    class Meta:
        abstract = True


class Creator(models.Model):
    """
    Abstract model for resource creators
    
    Represents individuals who created the resource. Stores personal information
    and identifiers. Will be linked to PublicationInfo via ManyToMany relationship.
    """
    family_name = models.CharField(max_length=255, null=False)
    given_name = models.CharField(max_length=255, null=True, blank=True)
    name_identifier = models.CharField(max_length=255, null=True, blank=True)
    name_identifier_type = models.CharField(
        max_length=20,
        choices=PersonIdentifierTypeChoices.choices,
        default=PersonIdentifierTypeChoices.ORCID,
        null=True,
        blank=True
    )
    affiliation = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        abstract = True


class Contributor(models.Model):
    """
    Abstract model for resource contributors
    
    Represents individuals who contributed to the resource in various roles.
    Extends Creator model with additional role information. Will be linked
    to PublicationInfo via ManyToMany relationship.
    """
    family_name = models.CharField(max_length=255, null=False)
    given_name = models.CharField(max_length=255, null=True, blank=True)
    name_identifier = models.CharField(max_length=255, null=True, blank=True)
    name_identifier_type = models.CharField(
        max_length=20,
        choices=PersonIdentifierTypeChoices.choices,
        default=PersonIdentifierTypeChoices.ORCID,
        null=True,
        blank=True
    )
    affiliation = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        abstract = True
