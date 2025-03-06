from django.db import models
from lacos.blam.models.base_indentifiers import AccessTypeChoices
from lacos.blam.models.base_model import BaseModel
from django.utils.translation import gettext_lazy as _

class AdministrativeInfo(BaseModel):
    """
    Abstract model for administrative metadata that will be publicly communicated,
    especially in regard to metacatalogues and user interfaces.
    """
    ACCESS_LEVELS = [
        ('embargo', _('Embargo - No access')),
        ('private', _('Private - Specific users only')),
        ('protected', _('Protected - All authenticated users')),
        ('public', _('Public - Everyone')),
    ]
    
    access_level = models.CharField(
        max_length=10,
        choices=ACCESS_LEVELS,
        default='public',
        help_text=_("Access level for this resource")
    )
    
    availability_date = models.DateField(
        null=False,
        help_text="Date at which the resource became or will become available (ISO 8601: YYYY-MM-DD)"
    )
    
    is_derivation_of = models.URLField(
        null=True,
        blank=True,
        help_text="URI that uniquely identifies the resource from which the current resource is derived"
    )
    
    # For private access level, we need to track authorized users
    authorized_users = models.ManyToManyField(
        'users.User',
        blank=True,
        related_name='%(class)s_authorized_resources',
        help_text=_("Users with explicit access to private resources")
    )
    
    is_identical_to = models.ManyToManyField(
        'IdenticalResource', 
        blank=True,
        related_name='%(app_label)s_%(class)s_identical_resources',
        help_text="URIs that uniquely identify identical resources"
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
        verbose_name = "Administrative Info"
        verbose_name_plural = "Administrative Info"


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
        verbose_name = "Identical Resource"
        verbose_name_plural = "Identical Resources"

    def __str__(self):
        return self.uri


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
        verbose_name = "License"
        verbose_name_plural = "Licenses"

    def __str__(self):
        return self.license_name


class RightsHolderIdentifier(BaseModel):
    """
    Abstract model for identifiers that uniquely identify rights holders.
    """
    IDENTIFIER_TYPES = [
        ('ORCID', 'ORCID'),
        ('ISNI', 'ISNI'),
        ('EMAIL', 'Email'),
        ('OTHER', 'Other'),
    ]
    
    identifier = models.CharField(
        max_length=255,
        help_text="Identifier for the rights holder"
    )
    identifier_type = models.CharField(
        max_length=10,
        choices=IDENTIFIER_TYPES,
        help_text="Type of the identifier"
    )

    class Meta:
        abstract = True
        verbose_name = "Rights Holder Identifier"
        verbose_name_plural = "Rights Holder Identifiers"

    def __str__(self):
        return f"{self.identifier_type}: {self.identifier}"


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
        verbose_name = "Rights Holder"
        verbose_name_plural = "Rights Holders"

    def __str__(self):
        return self.rights_holder_name
