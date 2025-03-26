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
    Cmd
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
    
    # Create base general info
    general_info = create_base_general_info(general_info_schema, location)
    
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


def create_base_general_info(general_info_schema, location: CollectionLocation) -> CollectionGeneralInfo:
    """
    Create and populate the base general info model.
    
    Args:
        general_info_schema: The general info section of the BLAM collection repository schema.
        location: The CollectionLocation instance to associate with the general info.
        
    Returns:
        A CollectionGeneralInfo instance with basic fields populated.
    """
    # Extract basic metadata
    display_title = general_info_schema.collection_display_title
    description = general_info_schema.collection_description
    version = general_info_schema.collection_version
    
    # Set the ID value and type from the first collection ID
    id_value = None
    id_type = None
    if general_info_schema.collection_id and len(general_info_schema.collection_id) > 0:
        first_id = general_info_schema.collection_id[0]
        id_value = first_id.value
        id_type = first_id.identifier_type.value
    
    # Create base general info
    general_info, created = CollectionGeneralInfo.objects.get_or_create(
        id_value=id_value,
        defaults={
            "display_title": display_title,
            "description": description,
            "version": version,
            "id_type": id_type,
            "location": location,
        },
    )
    
    # Update fields if the record already existed
    if not created:
        general_info.display_title = display_title
        general_info.description = description
        general_info.version = version
        general_info.id_type = id_type
        general_info.location = location
        general_info.save()
    
    return general_info


def import_keywords(general_info: CollectionGeneralInfo, keywords_schema) -> None:
    """
    Import keywords from the schema to the general info model.
    
    Args:
        general_info: The CollectionGeneralInfo instance to add keywords to.
        keywords_schema: The keywords section of the BLAM collection repository schema.
    """
    if keywords_schema and isinstance(keywords_schema, dict):
        for keyword_value in keywords_schema.get('collection_keyword', []):
            # Skip empty keywords
            if keyword_value and keyword_value.strip():
                keyword, created = CollectionKeyword.objects.get_or_create(value=keyword_value)
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
            # Prepare language data
            language_data = {
                'display_name': language_schema.object_language_display_name[0],
                'name': language_schema.object_language_name,
                'iso_639_3_code': language_schema.object_language_iso639_3_code.value,
                'glottolog_code': language_schema.object_language_glottolog_code.value
            }
            
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
                    # Skip empty alternative names
                    if alt_name_value and alt_name_value.strip():
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
            general_info.object_languages.add(language)
