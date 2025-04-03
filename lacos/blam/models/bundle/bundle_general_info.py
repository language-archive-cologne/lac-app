from django.db import models
from lacos.blam.models.base_general_info import (
    GeneralInfo, 
    Location, 
    Keyword, 
    ObjectLanguage, 
    ObjectLanguageAlternativeName,
    ObjectLanguageLanguageFamily,
    ObjectLanguageTaxonomy
)


class BundleGeneralInfo(GeneralInfo):
    """
    Concrete implementation of GeneralInfo for Bundle resources.
    
    Extends the abstract GeneralInfo model with bundle-specific fields
    and relationships.
    """
    keywords = models.ManyToManyField('BundleKeyword', blank=True)
    object_languages = models.ManyToManyField('BundleObjectLanguage', blank=True)
    location = models.ForeignKey('BundleLocation', on_delete=models.CASCADE, related_name='bundle_general_info')

    class Meta:
        verbose_name = "Bundle General Information"
        verbose_name_plural = "Bundle General Information"


class BundleLocation(Location):
    """
    Concrete implementation of Location for Bundle resources.
    
    Links location information to specific bundles.
    """

    class Meta:
        verbose_name = "Bundle Location"
        verbose_name_plural = "Bundle Locations"


class BundleKeyword(Keyword):
    """
    Concrete implementation of Keyword for Bundle resources.
    
    Note: This model may not be needed if using the ManyToManyField in 
    GeneralInfo directly with a concrete Keyword model.
    """
    class Meta:
        verbose_name = "Bundle Keyword"
        verbose_name_plural = "Bundle Keywords"


class BundleObjectLanguage(ObjectLanguage):
    """
    Concrete implementation of ObjectLanguage for Bundle resources.
    
    Represents a unique language entry.
    """
    alternative_names = models.ManyToManyField('BundleObjectLanguageAlternativeName', blank=True)
    
    class Meta:
        verbose_name = "Bundle Object Language"
        verbose_name_plural = "Bundle Object Languages"


class BundleObjectLanguageAlternativeName(ObjectLanguageAlternativeName):
    """
    Concrete implementation of ObjectLanguageAlternativeName for Bundle resources.
    """
    class Meta:
        verbose_name = "Bundle Object Language Alternative Name"
        verbose_name_plural = "Bundle Object Language Alternative Names"


class BundleObjectLanguageLanguageFamily(ObjectLanguageLanguageFamily):
    """
    Concrete implementation of ObjectLanguageLanguageFamily for Bundle resources.
    """
    class Meta:
        verbose_name = "Bundle Object Language Family"
        verbose_name_plural = "Bundle Object Language Families"


class BundleObjectLanguageTaxonomy(ObjectLanguageTaxonomy):
    """
    Concrete implementation of ObjectLanguageTaxonomy for Bundle resources.
    
    Links language taxonomy information to specific bundle object languages.
    """
    object_language = models.OneToOneField(
        'BundleObjectLanguage',
        on_delete=models.CASCADE,
        related_name='bundle_object_language_taxonomy'
    )
    language_family = models.ManyToManyField('BundleObjectLanguageLanguageFamily', blank=True)
    
    class Meta:
        verbose_name = "Bundle Object Language Taxonomy"
        verbose_name_plural = "Bundle Object Language Taxonomies"
