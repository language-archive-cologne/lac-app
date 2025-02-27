from django.db import models
from django.utils.translation import gettext_lazy as _


class ResourceTypeChoices(models.TextChoices):
    """Resource types based on CMDI ResourcetypeSimple"""
    METADATA = "METADATA", _("Metadata")
    RESOURCE = "RESOURCE", _("Resource")
    SEARCH_SERVICE = "SEARCH_SERVICE", _("Search Service")
    SEARCH_PAGE = "SEARCH_PAGE", _("Search Page")
    LANDING_PAGE = "LANDING_PAGE", _("Landing Page")


class IdentifierTypeChoices(models.TextChoices):
    """Common identifier types used across models"""
    DOI = "DOI", _("DOI")
    HANDLE = "HANDLE", _("Handle")
    URN = "URN", _("URN")
    OTHER = "OTHER", _("Other")


class PersonIdentifierTypeChoices(models.TextChoices):
    """Identifier types for people (creators, contributors, rights holders)"""
    ORCID = "ORCID", _("ORCID")
    ISNI = "ISNI", _("ISNI")
    EMAIL = "EMAIL", _("Email")
    OTHER = "OTHER", _("Other")


class FunderIdentifierTypeChoices(models.TextChoices):
    """Identifier types for funders"""
    CROSSREF_FUNDER = "CROSSREF_FUNDER", _("Crossref Funder")
    ISNI = "ISNI", _("ISNI")
    GRID = "GRID", _("GRID")
    OTHER = "OTHER", _("Other")


class AccessTypeChoices(models.TextChoices):
    """Access types for resources"""
    OPEN = "OPEN", _("Open")
    REGISTRATION_REQUIRED = "REGISTRATION_REQUIRED", _("Registration Required")
    REQUEST_REQUIRED = "REQUEST_REQUIRED", _("Request Required")
