from typing import Optional
from django.db.models import QuerySet
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd, BundleIdIdentifierType,
    ComplextypeBundleRecordingDate11 as BundleRecordingDateType,
    ComplextypeBundleCountryCode711 as BundleCountryCodeType,
    ComplextypeObjectLanguageIso6393Code0611 as ObjectLanguageIso639_3CodeType,
    ComplextypeObjectLanguageGlottologCode0611 as ObjectLanguageGlottologCodeType
)
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleLocation,
    BundleKeyword,
    BundleObjectLanguage,
    BundleObjectLanguageTaxonomy
)

# Type aliases for nested classes from the schema
BundleGeneralInfoType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo
BundleIdType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleId
BundleLocationType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleLocation
BundleKeywordsType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleKeywords
BundleObjectLanguagesType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages
BundleObjectLanguageType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage
ObjectLanguageAlternativeNamesType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageAlternativeNames
ObjectLanguageTaxonomyType = Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageTaxonomy


def export_general_info(general_info: BundleGeneralInfo, cmd_data: Cmd) -> None:
    """Export bundle general information from Django models to BLAM schema."""
    bundle_info = BundleGeneralInfoType()

    # Set basic fields
    bundle_info.bundle_display_title = general_info.display_title
    bundle_info.bundle_description = general_info.description
    bundle_info.bundle_version = general_info.version

    # Set bundle ID
    bundle_info.bundle_id = [create_bundle_id(general_info)]

    # Set recording date
    bundle_info.bundle_recording_date = create_recording_date(general_info.recording_date)

    # Set location
    bundle_info.bundle_location = export_bundle_location(general_info.location)

    # Set keywords if present
    if general_info.keywords.exists():
        bundle_info.bundle_keywords = export_keywords(general_info.keywords.all())

    # Set object languages
    bundle_info.bundle_object_languages = export_object_languages(general_info.object_languages.all())

    # Assign to cmd_data
    cmd_data.components.blam_bundle_repository_v1_0.bundle_general_info = bundle_info


def create_bundle_id(general_info: BundleGeneralInfo) -> BundleIdType:
    """Create a bundle ID object from the model."""
    bundle_id = BundleIdType()
    bundle_id.value = general_info.id_value
    bundle_id.identifier_type = map_to_schema_identifier_type(general_info.id_type)
    return bundle_id


def map_to_schema_identifier_type(id_type: str) -> BundleIdIdentifierType:
    """
    Map model identifier type to schema enum.
    
    Args:
        id_type: The identifier type from the model
        
    Returns:
        The corresponding schema identifier type enum value
    """
    mapping = {
        IdentifierTypeChoices.DOI.value: BundleIdIdentifierType.DOI,
        IdentifierTypeChoices.HANDLE.value: BundleIdIdentifierType.HANDLE,
        IdentifierTypeChoices.URN.value: BundleIdIdentifierType.URN,
        IdentifierTypeChoices.OTHER.value: BundleIdIdentifierType.OTHER,
    }
    return mapping.get(id_type, BundleIdIdentifierType.DOI)


def create_recording_date(date_value) -> BundleRecordingDateType:
    """Create a recording date object for the schema."""
    recording_date = BundleRecordingDateType()
    if date_value is None:
        recording_date.value = "Unknown"
    else:
        # Convert date object to ISO format string
        recording_date.value = date_value.isoformat() if hasattr(date_value, 'isoformat') else str(date_value)
    return recording_date


def export_bundle_location(location: BundleLocation) -> BundleLocationType:
    """
    Export a BundleLocation to schema format.
    
    Args:
        location: The BundleLocation instance
        
    Returns:
        A location object for the schema
    """
    location_data = BundleLocationType()
    
    # Set required fields
    location_data.bundle_region_name = location.region_name
    location_data.bundle_country_name = location.country_name
    
    # Create country code object
    country_code = BundleCountryCodeType()
    country_code.value = location.country_code
    location_data.bundle_country_code = country_code
    
    # Set facets
    location_data.bundle_region_facet = location.region_facet
    location_data.bundle_country_facet = location.country_facet
    
    # Set optional fields if they exist
    if location.geo_location:
        location_data.bundle_geo_location = location.geo_location
    if location.location_name:
        location_data.bundle_location_name = location.location_name
    if location.location_facet:
        location_data.bundle_location_facet = location.location_facet
    
    return location_data


def export_keywords(keywords: QuerySet[BundleKeyword]) -> BundleKeywordsType:
    """
    Export keywords to schema format.
    
    Args:
        keywords: QuerySet of BundleKeyword instances
        
    Returns:
        A keywords object for the schema
    """
    keywords_data = BundleKeywordsType()
    keywords_data.bundle_keyword = [keyword.value for keyword in keywords]
    return keywords_data


def export_object_languages(languages: QuerySet[BundleObjectLanguage]) -> BundleObjectLanguagesType:
    """
    Export object languages to schema format.
    
    Args:
        languages: QuerySet of BundleObjectLanguage instances
        
    Returns:
        An object languages container for the schema
    """
    languages_data = BundleObjectLanguagesType()
    languages_data.bundle_object_language = [
        export_object_language(language) for language in languages
    ]
    return languages_data


def export_object_language(language: BundleObjectLanguage) -> BundleObjectLanguageType:
    """
    Export a single object language to schema format.
    
    Args:
        language: The BundleObjectLanguage instance
        
    Returns:
        An object language for the schema
    """
    lang_data = BundleObjectLanguageType()
    
    # Set basic fields
    lang_data.object_language_display_name = language.display_name
    lang_data.object_language_name = language.name
    
    # Set ISO code if present
    if language.iso_639_3_code:
        iso_code = ObjectLanguageIso639_3CodeType()
        iso_code.value = language.iso_639_3_code
        lang_data.object_language_iso639_3_code = iso_code
    
    # Set Glottolog code if present
    if language.glottolog_code:
        glotto_code = ObjectLanguageGlottologCodeType()
        glotto_code.value = language.glottolog_code
        lang_data.object_language_glottolog_code = glotto_code
    
    # Add alternative names if present
    if language.alternative_names.exists():
        lang_data.object_language_alternative_names = export_alternative_names(language)
    
    # Add taxonomy if present
    try:
        taxonomy = language.bundle_object_language_taxonomy
        lang_data.object_language_taxonomy = export_language_taxonomy(taxonomy)
    except BundleObjectLanguageTaxonomy.DoesNotExist:
        pass
    
    return lang_data


def export_alternative_names(language: BundleObjectLanguage) -> ObjectLanguageAlternativeNamesType:
    """
    Export alternative names to schema format.
    
    Args:
        language: The BundleObjectLanguage instance with alternative names
        
    Returns:
        An alternative names container for the schema
    """
    alt_names = ObjectLanguageAlternativeNamesType()
    alt_names.object_language_alternative_name = [
        name.value for name in language.alternative_names.all()
    ]
    return alt_names


def export_language_taxonomy(taxonomy: BundleObjectLanguageTaxonomy) -> ObjectLanguageTaxonomyType:
    """
    Export language taxonomy to schema format.
    
    Args:
        taxonomy: The BundleObjectLanguageTaxonomy instance
        
    Returns:
        A taxonomy object for the schema
    """
    taxonomy_data = ObjectLanguageTaxonomyType()
    taxonomy_data.object_language_language_family = [
        family.value for family in taxonomy.language_family.all()
    ]
    return taxonomy_data
