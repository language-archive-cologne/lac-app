from typing import Any
from django.db import transaction
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionKeyword,
    CollectionObjectLanguage,
    CollectionObjectLanguageAlternativeName,
    CollectionObjectLanguageLanguageFamily,
    CollectionObjectLanguageTaxonomy
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
import logging

logger = logging.getLogger(__name__)


@transaction.atomic
def import_general_info(cmd_data: Any, collection: Collection) -> CollectionGeneralInfo:
    """
    Import general info from a BLAM collection repository schema to Django models.
    
    This function extracts general metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    location, keywords, and object languages.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        cmd_data: The parsed BLAM collection data containing general info.
        collection: The Collection instance to attach this general info to.
        
    Returns:
        A fully populated CollectionGeneralInfo instance with all related objects.
    """
    # Extract the general info section from the schema
    general_info_schema = cmd_data.components.blam_collection_repository_v1_2.collection_general_info
    
    # Create location first since it's required by general info
    location = create_location(general_info_schema.collection_location)
    
    # Create base general info with reference to collection
    general_info = create_base_general_info(general_info_schema, location, collection)
    
    # Reset related objects to keep updates idempotent
    general_info.keywords.clear()
    general_info.object_languages.all().delete()

    # Import related objects
    import_keywords(general_info, general_info_schema.collection_keywords)
    import_object_languages(general_info, general_info_schema.collection_object_languages)
    
    return general_info


def create_location(location_schema) -> CollectionLocation:
    """
    Create and populate a location model from schema data.
    
    Args:
        location_schema: The location section of the BLAM collection repository schema.
        
    Returns:
        A CollectionLocation instance with fields populated from the schema.
    """
    # Prepare location data
    location_data = {}
    
    # Set location fields if they exist in the schema
    if hasattr(location_schema, 'collection_geo_location') and location_schema.collection_geo_location:
        location_data['geo_location'] = location_schema.collection_geo_location
    
    if hasattr(location_schema, 'collection_location_name') and location_schema.collection_location_name:
        location_data['location_name'] = location_schema.collection_location_name
    
    if hasattr(location_schema, 'collection_location_facet') and location_schema.collection_location_facet:
        location_data['location_facet'] = location_schema.collection_location_facet
    
    if hasattr(location_schema, 'collection_region_name') and location_schema.collection_region_name:
        location_data['region_name'] = location_schema.collection_region_name
    
    if hasattr(location_schema, 'collection_region_facet') and location_schema.collection_region_facet:
        location_data['region_facet'] = location_schema.collection_region_facet
    
    if hasattr(location_schema, 'collection_country_name') and location_schema.collection_country_name:
        location_data['country_name'] = location_schema.collection_country_name
    
    if hasattr(location_schema, 'collection_country_facet') and location_schema.collection_country_facet:
        location_data['country_facet'] = location_schema.collection_country_facet
    
    if hasattr(location_schema, 'collection_country_code') and location_schema.collection_country_code:
        location_data['country_code'] = location_schema.collection_country_code.value
    
    # Try to find an existing location with the same data or create a new one
    # We use geo_location and country_code as unique identifiers
    unique_fields = {
        'geo_location': location_data.get('geo_location'),
        'country_code': location_data.get('country_code')
    }
    
    # Remove None values from unique fields
    unique_fields = {k: v for k, v in unique_fields.items() if v is not None}
    
    # If we have no unique fields, create a new location
    if not unique_fields:
        return CollectionLocation.objects.create(**location_data)
    
    # Try to get or create the location
    location, created = CollectionLocation.objects.get_or_create(
        **unique_fields,
        defaults=location_data
    )
    
    # Update fields if the record already existed
    if not created:
        for key, value in location_data.items():
            setattr(location, key, value)
        location.save()
    
    return location


def create_base_general_info(general_info_schema, location: CollectionLocation, collection: Collection) -> CollectionGeneralInfo:
    """
    Create and populate the base general info model.
    
    Args:
        general_info_schema: The general info section of the BLAM collection repository schema.
        location: The CollectionLocation instance to associate with the general info.
        collection: The Collection instance to attach this general info to.
        
    Returns:
        A CollectionGeneralInfo instance with basic fields populated.
    """
    # Extract basic metadata
    display_title = general_info_schema.collection_display_title
    description = general_info_schema.collection_description
    version = general_info_schema.collection_version
    
    # Set the ID value and type from the first collection ID
    id_value = None
    id_type_enum = None
    id_type_str = None # The string value to store

    if general_info_schema.collection_id and len(general_info_schema.collection_id) > 0:
        first_id = general_info_schema.collection_id[0]
        id_value = first_id.value
        id_type_enum = first_id.identifier_type # Get the enum e.g., CollectionIdIdentifierType.HANDLE
        
        if id_type_enum:
            # Map the enum name to the database value from IdentifierTypeChoices
            for choice_value, choice_name in IdentifierTypeChoices.choices:
                if id_type_enum.name == choice_value: # Compare enum name with DB value ('HANDLE' == 'HANDLE')
                    id_type_str = choice_value
                    break
            if not id_type_str:
                 logger.warning("Could not map Collection ID type enum to IdentifierTypeChoices, storing raw value", extra={"id_type_enum_name": id_type_enum.name})
                 # Fallback or raise error? Storing raw value from enum for now.
                 id_type_str = id_type_enum.value 
        else:
            logger.warning("Collection ID found but IdentifierType attribute is missing.")
            # Handle missing type? Default to OTHER?
            id_type_str = IdentifierTypeChoices.OTHER
    else:
        logger.warning("No Collection ID found in schema.")
        # Handle missing ID entirely? Maybe raise error depending on requirements

    try:
        # Try to find an existing general info for this collection
        general_info = CollectionGeneralInfo.objects.get(collection=collection)
        
        # Update fields
        general_info.display_title = display_title
        general_info.description = description
        general_info.version = version
        general_info.id_type = id_type_str
        general_info.id_value = id_value
        general_info.location = location
        general_info.save()
        
    except CollectionGeneralInfo.DoesNotExist:
        # Create a new general info if one doesn't exist
        general_info = CollectionGeneralInfo.objects.create(
            collection=collection,
            display_title=display_title,
            description=description,
            version=version,
            id_type=id_type_str,
            id_value=id_value,
            location=location
        )
    
    return general_info


def import_keywords(general_info: CollectionGeneralInfo, keywords_schema) -> None:
    """
    Import keywords from the schema to the general info model.
    
    Args:
        general_info: The CollectionGeneralInfo instance to add keywords to.
        keywords_schema: The keywords section of the BLAM collection repository schema.
    """
    if not keywords_schema:
        return
    keyword_values = getattr(keywords_schema, "collection_keyword", None) or []
    for keyword_value in keyword_values:
        if keyword_value and keyword_value.strip():
            keyword, _ = CollectionKeyword.objects.get_or_create(value=keyword_value)
            general_info.keywords.add(keyword)


def import_object_languages(general_info: CollectionGeneralInfo, object_languages_schema) -> None:
    """
    Import object languages from the schema to the general info model.
    
    This function creates CollectionObjectLanguage objects for each language in the schema
    and associates them with the general info model. It also imports alternative names
    and language family information.
    
    Args:
        general_info: The CollectionGeneralInfo instance to add object languages to.
        object_languages_schema: The object languages section of the BLAM collection repository schema.
    """
    if object_languages_schema and hasattr(object_languages_schema, 'collection_object_language'):
        for language_schema in object_languages_schema.collection_object_language:
            # Use iso_code as the primary identifier
            iso_code = getattr(language_schema.object_language_iso639_3_code, 'value', None)
            if not iso_code:
                logger.warning("Skipping language import: missing ISO 639-3 code in schema", extra={"language_name": language_schema.object_language_name})
                continue # Skip this language if it lacks the unique key

            # Create a new per-collection language object
            language = CollectionObjectLanguage.objects.create(
                iso_639_3_code=iso_code,
                display_name=language_schema.object_language_display_name[0] if language_schema.object_language_display_name else '',
                name=language_schema.object_language_name or '',
                glottolog_code=getattr(language_schema.object_language_glottolog_code, 'value', None) or '',
            )

            # Link the language to the current general_info
            general_info.object_languages.add(language)

            # Import alternative names if they exist
            if hasattr(language_schema, 'object_language_alternative_names') and language_schema.object_language_alternative_names:
                for alt_name_value in language_schema.object_language_alternative_names.object_language_alternative_name:
                    # Skip empty alternative names
                    if alt_name_value and alt_name_value.strip():
                        alt_name, created = CollectionObjectLanguageAlternativeName.objects.get_or_create(value=alt_name_value)
                        language.alternative_names.add(alt_name)
            
            # Import language taxonomy if it exists
            if hasattr(language_schema, 'object_language_taxonomy') and language_schema.object_language_taxonomy:
                taxonomy = CollectionObjectLanguageTaxonomy.objects.create(
                    object_language=language
                )
                
                # Add language families
                for family_value in language_schema.object_language_taxonomy.object_language_language_family:
                    family, created = CollectionObjectLanguageLanguageFamily.objects.get_or_create(value=family_value)
                    taxonomy.language_family.add(family)
