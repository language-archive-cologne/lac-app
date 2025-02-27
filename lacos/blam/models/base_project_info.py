from django.db import models
from base_indentifiers import FunderIdentifierTypeChoices

## projectinfo contains a single project

class ProjectInfo(models.Model):
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


class FunderIdentifier(models.Model):
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


class FunderInfo(models.Model):
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


