from django.db import transaction
from typing import Dict, Any, Optional, List
from lacos.blam.mappers.import_cleanup import (
    delete_unreferenced_records,
    detach_parent_m2m_children,
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_1 import (
    Cmd
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
def import_general_info(cmd_data: Cmd, bundle: 'Bundle') -> BundleGeneralInfo:
    """
    Import bundle general information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM bundle repository schema data
        bundle: The Bundle instance to associate the general info with
        
    Returns:
        The created BundleGeneralInfo instance
    """
    bundle_info = cmd_data.components.blam_bundle_repository_v1_1.bundle_general_info
    
    existing_general_info = BundleGeneralInfo.objects.filter(bundle=bundle).first()
    old_location_id = existing_general_info.location_id if existing_general_info else None

    # Create location first since it's needed as a foreign key
    location = create_bundle_location(bundle_info.bundle_location)
    
    # Create the main general info record
    general_info = create_bundle_general_info(bundle_info, location, bundle)
    
    detach_parent_m2m_children(general_info, "keywords")
    detach_parent_m2m_children(general_info, "object_languages")
    if old_location_id and old_location_id != location.pk:
        delete_unreferenced_records(BundleLocation, [old_location_id], ["bundle_general_info"])

    # Import keywords if present
    if bundle_info.bundle_keywords:
        import_keywords(general_info, bundle_info.bundle_keywords.bundle_keyword)
    
    # Import object languages (required in schema)
    import_object_languages(general_info, bundle_info.bundle_object_languages.bundle_object_language)
    
    return general_info


def create_bundle_general_info(bundle_info: Any, location: BundleLocation, bundle: 'Bundle' = None) -> BundleGeneralInfo:
    """
    Create a BundleGeneralInfo instance from schema data.
    
    Args:
        bundle_info: The bundle general info data from the schema
        location: The previously created BundleLocation instance
        bundle: The Bundle instance to associate the general info with
        
    Returns:
        The created BundleGeneralInfo instance
    """
    id_value = extract_id_value(bundle_info)
    id_type = extract_id_type(bundle_info)
    
    general_info = BundleGeneralInfo.objects.filter(bundle=bundle).first()
    if general_info:
        general_info.id_type = id_type
        general_info.id_value = id_value
        general_info.display_title = bundle_info.bundle_display_title
        general_info.description = bundle_info.bundle_description
        general_info.version = bundle_info.bundle_version
        general_info.recording_date = parse_recording_date(bundle_info.bundle_recording_date.value)
        general_info.location = location
        general_info.bundle = bundle
        general_info.save()
    else:
        general_info = BundleGeneralInfo.objects.create(
            id_type=id_type,
            id_value=id_value,
            display_title=bundle_info.bundle_display_title,
            description=bundle_info.bundle_description,
            version=bundle_info.bundle_version,
            recording_date=parse_recording_date(bundle_info.bundle_recording_date.value),
            location=location,
            bundle=bundle,
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


def map_identifier_type(id_type: Optional[Any]) -> str:
    """
    Map schema identifier type to model choices.
    
    Args:
        id_type: The identifier type from the schema
        
    Returns:
        The corresponding identifier type value for the model
    """
    if id_type is None:
        return IdentifierTypeChoices.DOI.value

    # Accept v1.0 enums, v1.1 enums, and plain strings by normalizing to one token.
    token = getattr(id_type, "name", None) or getattr(id_type, "value", None) or str(id_type)
    token = str(token).strip().upper().replace("-", "_").replace(" ", "_")
    if "." in token:
        token = token.split(".")[-1]

    mapping = {
        "DOI": IdentifierTypeChoices.DOI.value,
        "HANDLE": IdentifierTypeChoices.HANDLE.value,
        "URN": IdentifierTypeChoices.URN.value,
        "OTHER": IdentifierTypeChoices.OTHER.value,
    }
    return mapping.get(token, IdentifierTypeChoices.DOI.value)


def parse_recording_date(date_str: str) -> Optional[str]:
    """
    Parse recording date from schema format to Django model format.

    Handles partial dates by defaulting missing month/day to 01:
    - "2023" -> "2023-01-01"
    - "2023-05" -> "2023-05-01"
    - "2023-05-15" -> "2023-05-15"

    Args:
        date_str: The date string from the schema

    Returns:
        The parsed date in YYYY-MM-DD format, or None if "Unknown"
    """
    if date_str == "Unknown" or not date_str:
        return None

    # Handle partial dates
    parts = date_str.split('-')
    if len(parts) == 1:
        # Year only: "2023" -> "2023-01-01"
        return f"{parts[0]}-01-01"
    elif len(parts) == 2:
        # Year and month: "2023-05" -> "2023-05-01"
        return f"{parts[0]}-{parts[1]}-01"
    else:
        # Full date or unexpected format - return as-is
        return date_str


def create_bundle_location(location_data: Any) -> BundleLocation:
    """
    Create a BundleLocation instance from schema data.
    
    Args:
        location_data: The location data from the schema
        
    Returns:
        The created BundleLocation instance
    """
    return BundleLocation.objects.create(
        region_name=location_data.bundle_region_name,
        country_name=location_data.bundle_country_name,
        country_code=location_data.bundle_country_code.value,
        geo_location=getattr(location_data, 'bundle_geo_location', None),
        location_name=getattr(location_data, 'bundle_location_name', None),
        location_facet=getattr(location_data, 'bundle_location_facet', None),
        region_facet=location_data.bundle_region_facet,
        country_facet=location_data.bundle_country_facet,
    )


def import_keywords(general_info: BundleGeneralInfo, keywords: List[str]) -> None:
    """
    Import keywords from schema data to BundleKeyword models.
    
    Args:
        general_info: The BundleGeneralInfo instance to associate keywords with
        keywords: List of keyword strings from the schema
    """
    for keyword_value in keywords:
        keyword = BundleKeyword.objects.create(value=keyword_value)
        general_info.keywords.add(keyword)


def import_object_languages(general_info: BundleGeneralInfo, languages: List[Any]) -> None:
    """
    Import object languages from schema data to BundleObjectLanguage models.
    
    Args:
        general_info: The BundleGeneralInfo instance to associate languages with
        languages: List of language data objects from the schema
    """
    for lang_data in languages:
        language = create_object_language(lang_data)

        # If language object was successfully obtained/created, link it
        if language:
            general_info.object_languages.add(language)

            # Add alternative names if present
            if hasattr(lang_data, 'object_language_alternative_names') and lang_data.object_language_alternative_names:
                add_alternative_names(language, lang_data.object_language_alternative_names.object_language_alternative_name)
            
            # Add language taxonomy if present
            if hasattr(lang_data, 'object_language_taxonomy') and lang_data.object_language_taxonomy:
                create_language_taxonomy(language, lang_data.object_language_taxonomy)


def create_object_language(lang_data: Any) -> Optional[BundleObjectLanguage]:
    """Create a per-bundle BundleObjectLanguage instance.

    Args:
        lang_data: The language data from the schema

    Returns:
        The created BundleObjectLanguage instance, or None if no ISO code.
    """
    iso_code = getattr(lang_data.object_language_iso639_3_code, 'value', None)
    if not iso_code:
        return None

    language = BundleObjectLanguage.objects.create(
        iso_639_3_code=iso_code,
        display_name=lang_data.object_language_display_name or '',
        name=lang_data.object_language_name or '',
        glottolog_code=getattr(lang_data.object_language_glottolog_code, 'value', None) or '',
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
    taxonomy = BundleObjectLanguageTaxonomy.objects.create(object_language=language)
    
    for family_name in taxonomy_data.object_language_language_family:
        family, created = BundleObjectLanguageLanguageFamily.objects.get_or_create(value=family_name)
        taxonomy.language_family.add(family)
    
    return taxonomy
