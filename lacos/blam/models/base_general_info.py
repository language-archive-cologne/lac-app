from django.db import models
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.base_model import BaseModel

class GeneralInfo(BaseModel):
    """
    Abstract base model containing common general information fields.
    
    This model provides shared fields used by both BundleGeneralInfo and CollectionGeneralInfo.
    Contains core metadata like identifiers, title, description, keywords and version info.
    id_value must be unique across all resources
    """
    # Identifier fields for the resource
    id_value = models.CharField(max_length=255, null=False, unique=True)
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
    Abstract model for languages in the collection or bundle.
    
    Stores comprehensive language metadata including standard codes (ISO, Glottolog),
    various names/labels, and relationships to alternative names. Concrete implementations
    will link to either BundleGeneralInfo or CollectionGeneralInfo.

    Requirements:
    - Both ISO and Glottolog codes must be provided for each language (not null)
    - ISO codes must be unique across all records
    - Glottolog codes must be unique across all records
    - Name must also be provided (not null)
    """
    display_name = models.CharField(max_length=255, null=False)
    name = models.CharField(max_length=255, null=False, blank=False)
    iso_639_3_code = models.CharField(max_length=3, null=False, blank=False, unique=True)
    glottolog_code = models.CharField(max_length=10, null=False, blank=False, unique=True)
    alternative_names = models.ManyToManyField('ObjectLanguageAlternativeName', blank=True)
    
    class Meta:
        abstract = True
        unique_together = [('name', 'iso_639_3_code', 'glottolog_code')]
    
    def clean(self):
        """
        Custom validation to ensure all required fields are provided.
        """
        super().clean()
        
        # All fields should be non-null as per model definition,
        # but we'll add an extra check here for clarity
        if not self.name or not self.iso_639_3_code or not self.glottolog_code:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                "Name, ISO 639-3 code, and Glottolog code must all be provided."
            )


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
