from django.db import models
from lacos.blam.models.base_general_info import (
    GeneralInfo,
    Location,
    Keyword,
    ObjectLanguage,
    ObjectLanguageAlternativeName,
    ObjectLanguageLanguageFamily,
    ObjectLanguageTaxonomy,
)


class CollectionGeneralInfo(GeneralInfo):
    """
    Concrete implementation of GeneralInfo for Collections.
    
    Extends the abstract GeneralInfo model to provide collection-specific
    general information and metadata.
    """
    collection_keywords = models.ManyToManyField('CollectionKeyword', blank=True)
    collection_object_languages = models.ManyToManyField('CollectionObjectLanguage', blank=True)
    collection_location = models.ForeignKey('CollectionLocation', on_delete=models.CASCADE, related_name='collection_general_info')

    class Meta:
        verbose_name = "Collection General Info"
        verbose_name_plural = "Collection General Info"

class CollectionLocation(Location):
    """
    Concrete implementation of Location for Collections.
    
    Links location information to a specific collection.
    """
    class Meta:
        verbose_name = "Collection Location"
        verbose_name_plural = "Collection Locations"

class CollectionKeyword(Keyword):
    """
    Concrete implementation of Keyword for Collections.
    
    Used to categorize and enable discovery of collections.
    """
    
    class Meta:
        verbose_name = "Collection Keyword"
        verbose_name_plural = "Collection Keywords"


class CollectionObjectLanguage(ObjectLanguage):
    """
    Concrete implementation of ObjectLanguage for Collections.
    
    Represents languages that are the subject of study in a collection.
    """

    alternative_names = models.ManyToManyField('CollectionObjectLanguageAlternativeName', blank=True)
    
    class Meta:
        verbose_name = "Collection Object Language"
        verbose_name_plural = "Collection Object Languages"


class CollectionObjectLanguageAlternativeName(ObjectLanguageAlternativeName):
    """
    Concrete implementation of ObjectLanguageAlternativeName for Collections.
    
    Captures different names or variants of languages in a collection.
    """
    
    class Meta:
        verbose_name = "Collection Object Language Alternative Name"
        verbose_name_plural = "Collection Object Language Alternative Names"


class CollectionObjectLanguageLanguageFamily(ObjectLanguageLanguageFamily):
    """
    Concrete implementation of ObjectLanguageLanguageFamily for Collections.
    
    Represents language families for languages in a collection.
    """
    
    class Meta:
        verbose_name = "Collection Object Language Family"
        verbose_name_plural = "Collection Object Language Families"


class CollectionObjectLanguageTaxonomy(ObjectLanguageTaxonomy):
    """
    Concrete implementation of ObjectLanguageTaxonomy for Collections.
    
    Enables organization of collection languages into hierarchical family relationships.
    """
    object_language = models.OneToOneField(
        CollectionObjectLanguage,
        on_delete=models.CASCADE,
        related_name='taxonomy'
    )
    language_family = models.ManyToManyField('CollectionObjectLanguageLanguageFamily', blank=True)
    
    class Meta:
        verbose_name = "Collection Object Language Taxonomy"
        verbose_name_plural = "Collection Object Language Taxonomies"
