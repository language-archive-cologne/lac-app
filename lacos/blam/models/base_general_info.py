from django.db import models
from base_general_info import IdentifierTypeChoices
from .base_model import BaseModel

class GeneralInfo(BaseModel):
    """
    Abstract base model containing common general information fields.
    
    This model provides shared fields used by both BundleGeneralInfo and CollectionGeneralInfo.
    Contains core metadata like identifiers, title, description, keywords and version info.
    """
    # Identifier fields for the resource
    id_value = models.CharField(max_length=255, null=False)
    id_type = models.CharField(
        max_length=20,
        choices=IdentifierTypeChoices.choices,
        default=IdentifierTypeChoices.DOI,
        null=False
    )
    
    # Core metadata fields
    display_title = models.CharField(max_length=255, null=False)
    description = models.TextField(null=False)
    keywords = models.ManyToManyField('Keyword', blank=True)
    
    # Version tracking
    version = models.CharField(max_length=50, null=False)

    class Meta:
        abstract = True


class Location(BaseModel):
    """
    Abstract model for storing hierarchical location information.
    
    Captures location details at multiple levels - from specific geographic coordinates
    to country-level information. Includes both human-readable names and faceted values
    for search/filtering.
    """
    geo_location = models.CharField(max_length=255, null=True, blank=True)
    location_name = models.CharField(max_length=255, null=True, blank=True)
    location_facet = models.CharField(max_length=255, null=True, blank=True)
    region_name = models.CharField(max_length=255, null=True, blank=True)
    region_facet = models.CharField(max_length=255, null=True, blank=True)
    country_name = models.CharField(max_length=255, null=True, blank=True)
    country_facet = models.CharField(max_length=255, null=True, blank=True)
    country_code = models.CharField(max_length=2, null=True, blank=True)
    
    class Meta:
        abstract = True


class Keyword(BaseModel):
    """
    Abstract model for resource keywords/tags.
    
    Used to categorize and enable discovery of resources. Concrete implementations
    will establish relationships to either BundleGeneralInfo or CollectionGeneralInfo
    through foreign keys.
    """
    value = models.CharField(max_length=255, null=False)
    
    class Meta:
        abstract = True


class ObjectLanguage(BaseModel):
    """
    Abstract model for languages that are the subject of study.
    
    Stores comprehensive language metadata including standard codes (ISO, Glottolog),
    various names/labels, and relationships to alternative names. Concrete implementations
    will link to either BundleGeneralInfo or CollectionGeneralInfo.
    """
    display_name = models.CharField(max_length=255, null=False)
    name = models.CharField(max_length=255, null=True, blank=True)
    iso_639_3_code = models.CharField(max_length=3, null=True, blank=True)
    glottolog_code = models.CharField(max_length=10, null=True, blank=True)
    alternative_names = models.ManyToManyField('ObjectLanguageAlternativeName', blank=True)
    
    class Meta:
        abstract = True


class ObjectLanguageAlternativeName(BaseModel):
    """
    Abstract model for alternative names/variants of object languages.
    
    Captures different names, spellings or representations of the same language.
    Helps improve discoverability by storing known language name variations.
    """
    value = models.CharField(max_length=255, null=False)
    
    class Meta:
        abstract = True


class ObjectLanguageLanguageFamily(BaseModel):
    """
    Abstract model representing language families.
    
    Used to classify and group related languages according to their genealogical relationships.
    Concrete implementations will establish relationships to ObjectLanguage instances.
    """
    value = models.CharField(max_length=255, null=False)
    
    class Meta:
        abstract = True

class ObjectLanguageTaxonomy(BaseModel):
    """
    Abstract model for language taxonomic classification.
    
    Enables organization of languages into hierarchical family relationships
    through many-to-many relationships with language families.
    """
    language_family = models.ManyToManyField('ObjectLanguageLanguageFamily', blank=True)
    
    class Meta:
        abstract = True
