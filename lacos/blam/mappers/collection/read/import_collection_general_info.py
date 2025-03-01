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
from blam_schemas.collection.blam_collection_repository_v1_0 import (
    Cmd,
    CollectionIdIdentifierType
)


@transaction.atomic
def import_general_info(collection_schema: Cmd) -> CollectionGeneralInfo:
    """
    Import general info from a BLAM collection repository schema to Django models.
    
    This function extracts general metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    location, keywords, and object languages.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        collection_schema: The BLAM collection repository schema containing general info.
        
    Returns:
        A fully populated CollectionGeneralInfo instance with all related objects.
    """
    # Extract the general info section from the schema
    general_info_schema = collection_schema.components.blam_collection_repository_v1_0.collection_general_info
    
    # Create location first since it's required by general info
    location = create_location(general_info_schema.collection_location)
    
    # Create and populate the general info model
    general_info = create_base_general_info(general_info_schema, location)
    
    # Import related objects
    import_keywords(general_info, general_info_schema)
    import_object_languages(general_info, general_info_schema)
    
    general_info.save()
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
    
    # Create a new location (we don't use get_or_create here as locations are typically unique per collection)
    location = CollectionLocation.objects.create(**location_data)
    return location


def create_base_general_info(general_info_schema, location: CollectionLocation) -> CollectionGeneralInfo:
    """
    Create and populate the base general info model.
    
    Args:
        general_info_schema: The general info section of the BLAM collection repository schema.
        location: The CollectionLocation instance to associate with the general info.
        
    Returns:
        A CollectionGeneralInfo instance with basic fields populated.
    """
    # Prepare general info data
    general_info_data = {
        'collection_location': location
    }
    
    # Set the ID value and type from the first collection ID
    if general_info_schema.collection_id and len(general_info_schema.collection_id) > 0:
        first_id = general_info_schema.collection_id[0]
        general_info_data['id_value'] = first_id.value
        
        # Map the ID type from schema to model
        id_type_mapping = {
            CollectionIdIdentifierType.DOI: "doi",
            CollectionIdIdentifierType.HANDLE: "handle",
            CollectionIdIdentifierType.URN: "urn",
            CollectionIdIdentifierType.OTHER: "other"
        }
        general_info_data['id_type'] = id_type_mapping.get(first_id.identifier_type, "doi")
    
    # Set the version
    if general_info_schema.collection_version:
        general_info_data['version'] = general_info_schema.collection_version
    
    # Set the display title
    if general_info_schema.collection_display_title:
        general_info_data['display_title'] = general_info_schema.collection_display_title
    
    # Set the description
    if general_info_schema.collection_description:
        general_info_data['description'] = general_info_schema.collection_description
    
    # Create a new general info (we don't use get_or_create as general info is typically unique per collection)
    general_info = CollectionGeneralInfo.objects.create(**general_info_data)
    return general_info


def import_keywords(general_info: CollectionGeneralInfo, general_info_schema) -> None:
    """
    Import keywords from the schema to the general info model.
    
    Args:
        general_info: The CollectionGeneralInfo instance to add keywords to.
        general_info_schema: The general info section of the BLAM collection repository schema.
    """
    if hasattr(general_info_schema, 'collection_keywords') and general_info_schema.collection_keywords:
        for keyword_value in general_info_schema.collection_keywords.collection_keyword:
            keyword, created = CollectionKeyword.objects.get_or_create(value=keyword_value)
            general_info.collection_keywords.add(keyword)


def import_object_languages(general_info: CollectionGeneralInfo, general_info_schema) -> None:
    """
    Import object languages from the schema to the general info model.
    
    This function creates CollectionObjectLanguage objects for each language in the schema
    and associates them with the general info model. It also imports alternative names
    and language family information.
    
    Args:
        general_info: The CollectionGeneralInfo instance to add object languages to.
        general_info_schema: The general info section of the BLAM collection repository schema.
    """
    if hasattr(general_info_schema, 'collection_object_languages') and general_info_schema.collection_object_languages:
        for language_schema in general_info_schema.collection_object_languages.collection_object_language:
            # Prepare language data
            language_data = {
                'display_name': language_schema.object_language_display_name
            }
            
            # Set optional fields if they exist
            if hasattr(language_schema, 'object_language_name') and language_schema.object_language_name:
                language_data['name'] = language_schema.object_language_name
            
            if hasattr(language_schema, 'object_language_iso639_3_code') and language_schema.object_language_iso639_3_code:
                language_data['iso_639_3_code'] = language_schema.object_language_iso639_3_code.value
            
            if hasattr(language_schema, 'object_language_glottolog_code') and language_schema.object_language_glottolog_code:
                language_data['glottolog_code'] = language_schema.object_language_glottolog_code.value
            
            # Try to find an existing language with the same display name and codes, or create a new one
            language, created = CollectionObjectLanguage.objects.get_or_create(
                display_name=language_data['display_name'],
                defaults=language_data
            )
            
            # Update any fields that might have changed
            if not created:
                for key, value in language_data.items():
                    setattr(language, key, value)
                language.save()
            
            # Import alternative names if they exist
            if hasattr(language_schema, 'object_language_alternative_names') and language_schema.object_language_alternative_names:
                for alt_name_value in language_schema.object_language_alternative_names.object_language_alternative_name:
                    alt_name, created = CollectionObjectLanguageAlternativeName.objects.get_or_create(value=alt_name_value)
                    language.alternative_names.add(alt_name)
            
            # Import language taxonomy if it exists
            if hasattr(language_schema, 'object_language_taxonomy') and language_schema.object_language_taxonomy:
                # Try to get existing taxonomy or create a new one
                taxonomy, created = CollectionObjectLanguageTaxonomy.objects.get_or_create(
                    object_language=language
                )
                
                # Add language families
                for family_value in language_schema.object_language_taxonomy.object_language_language_family:
                    family, created = CollectionObjectLanguageLanguageFamily.objects.get_or_create(value=family_value)
                    taxonomy.language_family.add(family)
            
            # Add the language to the general info
            general_info.collection_object_languages.add(language)
