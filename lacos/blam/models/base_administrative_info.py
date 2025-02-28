from django.db import models
from base_indentifiers import AccessTypeChoices
from .base_model import BaseModel

class AdministrativeInfo(BaseModel):
    """
    Abstract model for administrative metadata that will be publicly communicated,
    especially in regard to metacatalogues and user interfaces.
    """
    is_identical_to = models.ManyToManyField(
        'IdenticalResource', 
        blank=True,
        related_name='%(app_label)s_%(class)s_identical_resources',
        help_text="URIs that uniquely identify identical resources"
    )
    is_derivation_of = models.URLField(
        null=True,
        blank=True,
        help_text="URI that uniquely identifies the resource from which the current resource is derived"
    )
    availability_date = models.DateField(
        null=False,
        help_text="Date at which the resource became or will become available (ISO 8601: YYYY-MM-DD)"
    )
    licenses = models.ManyToManyField(
        'License',
        related_name='%(app_label)s_%(class)s_licenses',
        help_text="Licenses under which the resource is available"
    )
    rights_holders = models.ManyToManyField(
        'RightsHolder',
        related_name='%(app_label)s_%(class)s_rights_holders',
        help_text="Individuals or institutions owning or managing the rights over the resource"
    )
    
    class Meta:
        abstract = True


class IdenticalResource(BaseModel):
    """
    Abstract model for resources that are identical to the current resource.
    """
    uri = models.URLField(
        null=False,
        help_text="URI that uniquely identifies an identical resource"
    )
    
    class Meta:
        abstract = True


class License(BaseModel):
    """
    Abstract model for license information under which the resource is available.
    """
    license_name = models.CharField(
        max_length=255,
        null=False,
        help_text="Complete human readable name of the license including version information if applicable"
    )
    license_identifier = models.URLField(
        null=False,
        help_text="URI for the license"
    )
    access = models.CharField(
        max_length=30,
        choices=AccessTypeChoices.choices,
        default=AccessTypeChoices.OPEN,
        null=False,
        help_text="Terms of availability of the resource"
    )
    
    class Meta:
        abstract = True


class RightsHolderIdentifier(BaseModel):
    """
    Abstract model for identifiers that uniquely identify rights holders.
    """
    value = models.URLField(
        null=False,
        help_text="URI that uniquely identifies the rights holder"
    )
    
    class Meta:
        abstract = True


class RightsHolder(BaseModel):
    """
    Abstract model for information about the individual or institution 
    owning or managing the rights in regard to the resource.
    """
    rights_holder_name = models.CharField(
        max_length=255,
        null=False,
        help_text="Name of the individual or institution owning or managing the rights over the resource"
    )
    rights_holder_identifiers = models.ManyToManyField(
        'RightsHolderIdentifier',
        blank=True,
        related_name='%(app_label)s_%(class)s_rights_holders',
        help_text="Identifiers for the rights holder"
    )
    
    class Meta:
        abstract = True
