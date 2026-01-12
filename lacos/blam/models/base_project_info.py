from django.db import models
from lacos.blam.models.base_indentifiers import FunderIdentifierTypeChoices
from lacos.blam.models.base_model import BaseModel

"""
Unlike other base models in this package which are abstract and extended by collection/bundle
specific implementations, ProjectInfo is a concrete model that is shared and referenced by
both collections and bundles. This allows project information to be consistently maintained
across different types of resources that are part of the same project.
"""


class ProjectInfo(BaseModel):
    """
    Model for descriptive information about a project relating to bundle data.
    """
    project_display_name = models.CharField(
        max_length=255, 
        null=False,
        help_text="Human readable name of the project, preferably the common abbreviation"
    )
    project_description = models.TextField(
        null=False,
        help_text="Human readable description of the project including full project name"
    )

    funder_infos = models.ManyToManyField('FunderInfo', related_name='projects')

    def __str__(self) -> str:
        return self.project_display_name


class FunderIdentifier(BaseModel):
    """
    Model for identifiers that uniquely identify funding bodies.
    """
    value = models.URLField(
        null=False,
        help_text="URI that uniquely identifies the funding body"
    )
    identifier_type = models.CharField(
        max_length=20,
        choices=FunderIdentifierTypeChoices.choices,
        default=FunderIdentifierTypeChoices.CROSSREF_FUNDER,
        null=False,
        help_text="The identifier type used"
    )

    def __str__(self) -> str:
        return f"{self.identifier_type}: {self.value}"


class FunderInfo(BaseModel):
    """
    Model for information about a funding organization associated with this resource.
    """
    funder_name = models.CharField(
        max_length=255,
        null=False,
        help_text="Name of the funding organization, preferably the common abbreviation"
    )
    grant_identifier = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Identifier that uniquely identifies the grant according to an established scheme"
    )
    grant_uri = models.URLField(
        null=True,
        blank=True,
        help_text="URI that uniquely identifies the grant and funding body"
    )
    funder_identifiers = models.ManyToManyField(
        'FunderIdentifier',
        blank=True,
        related_name='funder_infos',
        help_text="Identifiers for the funding organization"
    )

    def __str__(self) -> str:
        return self.funder_name
