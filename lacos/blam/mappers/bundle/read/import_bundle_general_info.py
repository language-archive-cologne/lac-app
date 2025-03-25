from django.db import transaction
from enum import Enum
from typing import Dict, Any, Optional, List
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd, BundleIdIdentifierType
)
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleLocation,
    BundleKeyword,
    BundleObjectLanguage,
    BundleObjectLanguageAlternativeName,
    BundleObjectLanguageLanguageFamily,
    BundleObjectLanguageTaxonomy
)



@transaction.atomic
def import_general_info(cmd_data: Cmd) -> BundleGeneralInfo:
    """
    Import bundle general information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM bundle repository schema data
        
    Returns:
        The created BundleGeneralInfo instance
    """
    bundle_info = cmd_data.components.blam_bundle_repository_v1_0.bundle_general_info
    
    # Create location first since it's needed as a foreign key
    location = create_bundle_location(bundle_info.bundle_location)
    
    # Create the main general info record
    general_info = create_bundle_general_info(bundle_info, location)
    
    # Import keywords if present
    if bundle_info.bundle_keywords:
        import_keywords(general_info, bundle_info.bundle_keywords.bundle_keyword)
    
    # Import object languages (required in schema)
    import_object_languages(general_info, bundle_info.bundle_object_languages.bundle_object_language)
    
    return general_info


def create_bundle_general_info(bundle_info: Any, location: BundleLocation) -> BundleGeneralInfo:
    """
    Create a BundleGeneralInfo instance from schema data.
    
    Args:
        bundle_info: The bundle general info data from the schema
        location: The previously created BundleLocation instance
        
    Returns:
        The created BundleGeneralInfo instance
    """
    id_value = extract_id_value(bundle_info)
    id_type = extract_id_type(bundle_info)
    
    general_info, created = BundleGeneralInfo.objects.get_or_create(
        id_value=id_value,
        id_type=id_type,
        defaults={
            'display_title': bundle_info.bundle_display_title,
            'description': bundle_info.bundle_description,
            'version': bundle_info.bundle_version,
            'recording_date': parse_recording_date(bundle_info.bundle_recording_date.value),
            'location': location
        }
    )
    return general_info


def extract_id_value(bundle_info: Any) -> str:
    """
    Extract the ID value from the bundle info.
    
    Args:
        bundle_info: The bundle general info data from the schema
        
    Returns:
        The ID value as a string
    """
    # Get the first bundle ID (required in schema)
    return bundle_info.bundle_id[0].value


def extract_id_type(bundle_info: Any) -> str:
    """
    Extract and map the ID type from the bundle info.
    
    Args:
        bundle_info: The bundle general info data from the schema
        
    Returns:
        The mapped ID type as a string
    """
    return map_identifier_type(bundle_info.bundle_id[0].identifier_type)


def map_identifier_type(id_type: Optional[BundleIdIdentifierType]) -> str:
    """
    Map schema identifier type to model choices.
    
    Args:
        id_type: The identifier type from the schema
        
    Returns:
        The corresponding identifier type value for the model
    """
    if id_type is None:
        return IdentifierTypeChoices.DOI.value
    
    mapping = {
        BundleIdIdentifierType.DOI: IdentifierTypeChoices.DOI.value,
        BundleIdIdentifierType.HANDLE: IdentifierTypeChoices.HANDLE.value,
        BundleIdIdentifierType.URN: IdentifierTypeChoices.URN.value,
        BundleIdIdentifierType.OTHER: IdentifierTypeChoices.OTHER.value,
    }
    
    # Convert string to enum if needed
    if isinstance(id_type, str):
        try:
            id_type = BundleIdIdentifierType(id_type)
        except ValueError:
            return IdentifierTypeChoices.DOI.value
    
    return mapping.get(id_type, IdentifierTypeChoices.DOI.value)


def parse_recording_date(date_str: str) -> Optional[str]:
    """
    Parse recording date from schema format to Django model format.
    
    Args:
        date_str: The date string from the schema
        
    Returns:
        The parsed date or None if "Unknown"
    """
    if date_str == "Unknown":
        return None
    return date_str


def create_bundle_location(location_data: Any) -> BundleLocation:
    """
    Create a BundleLocation instance from schema data.
    
    Args:
        location_data: The location data from the schema
        
    Returns:
        The created BundleLocation instance
    """
    location, created = BundleLocation.objects.get_or_create(
        region_name=location_data.bundle_region_name,
        country_name=location_data.bundle_country_name,
        country_code=location_data.bundle_country_code.value,
        defaults={
            'geo_location': getattr(location_data, 'bundle_geo_location', None),
            'location_name': getattr(location_data, 'bundle_location_name', None),
            'location_facet': getattr(location_data, 'bundle_location_facet', None),
            'region_facet': location_data.bundle_region_facet,
            'country_facet': location_data.bundle_country_facet,
        }
    )
    return location


def import_keywords(general_info: BundleGeneralInfo, keywords: List[str]) -> None:
    """
    Import keywords from schema data to BundleKeyword models.
    
    Args:
        general_info: The BundleGeneralInfo instance to associate keywords with
        keywords: List of keyword strings from the schema
    """
    for keyword_value in keywords:
        keyword, created = BundleKeyword.objects.get_or_create(value=keyword_value)
        general_info.keywords.add(keyword)


def import_object_languages(general_info: BundleGeneralInfo, languages: List[Any]) -> None:
    """
    Import object languages from schema data to BundleObjectLanguage models.
    
    Args:
        general_info: The BundleGeneralInfo instance to associate languages with
        languages: List of language data objects from the schema
    """
    for lang_data in languages:
        language = create_object_language(general_info, lang_data)
        
        # Add alternative names if present
        if hasattr(lang_data, 'object_language_alternative_names') and lang_data.object_language_alternative_names:
            add_alternative_names(language, lang_data.object_language_alternative_names.object_language_alternative_name)
        
        # Add language taxonomy if present
        if hasattr(lang_data, 'object_language_taxonomy') and lang_data.object_language_taxonomy:
            create_language_taxonomy(language, lang_data.object_language_taxonomy)


def create_object_language(general_info: BundleGeneralInfo, lang_data: Any) -> BundleObjectLanguage:
    """
    Create a BundleObjectLanguage instance from schema data.
    
    Args:
        general_info: The BundleGeneralInfo instance to associate with
        lang_data: The language data from the schema
        
    Returns:
        The created BundleObjectLanguage instance
    """
    language, created = BundleObjectLanguage.objects.get_or_create(
        bundle=general_info,
        display_name=lang_data.object_language_display_name,
        defaults={
            'name': lang_data.object_language_name,
            'iso_639_3_code': getattr(lang_data.object_language_iso639_3_code, 'value', None),
            'glottolog_code': getattr(lang_data.object_language_glottolog_code, 'value', None)
        }
    )
    return language


def add_alternative_names(language: BundleObjectLanguage, alt_names: List[str]) -> None:
    """
    Add alternative names to a language.
    
    Args:
        language: The BundleObjectLanguage instance to associate names with
        alt_names: List of alternative name strings from the schema
    """
    for alt_name in alt_names:
        alt_name_obj, created = BundleObjectLanguageAlternativeName.objects.get_or_create(value=alt_name)
        language.alternative_names.add(alt_name_obj)


def create_language_taxonomy(language: BundleObjectLanguage, taxonomy_data: Any) -> BundleObjectLanguageTaxonomy:
    """
    Create a language taxonomy from schema data.
    
    Args:
        language: The BundleObjectLanguage instance to associate with
        taxonomy_data: The taxonomy data from the schema
        
    Returns:
        The created BundleObjectLanguageTaxonomy instance
    """
    taxonomy, created = BundleObjectLanguageTaxonomy.objects.get_or_create(object_language=language)
    
    for family_name in taxonomy_data.object_language_language_family:
        family, created = BundleObjectLanguageLanguageFamily.objects.get_or_create(value=family_name)
        taxonomy.language_family.add(family)
    
    return taxonomy
