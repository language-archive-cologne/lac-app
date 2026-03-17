from typing import Any
from django.db import transaction
from lacos.blam.mappers.import_cleanup import detach_parent_m2m_children
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionPublicationInfoCreator,
    CollectionCreator,
    CollectionContributor,
)
from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_2 import (
    CreatorNameIdentifierIdentifierType,
    ContributorNameIdentifierIdentifierType
)


@transaction.atomic
def import_publication_info(cmd_data: Any, collection: Collection) -> CollectionPublicationInfo:
    """
    Import publication info from a BLAM collection repository schema to Django models.
    
    This function extracts publication metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    creators and contributors.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        cmd_data: The parsed BLAM collection data containing publication info.
        collection: The Collection instance to attach this publication info to.
        
    Returns:
        A fully populated CollectionPublicationInfo instance with all related objects.
    """
    # Extract the publication info section from the schema
    publication_info_schema = cmd_data.components.blam_collection_repository_v1_2.collection_publication_info
    
    # Create and populate the publication info model
    publication_info = create_base_publication_info(publication_info_schema, collection)
    
    detach_parent_m2m_children(publication_info, "creators")
    detach_parent_m2m_children(publication_info, "contributors")

    # Import creators
    import_creators(publication_info, publication_info_schema)
    
    # Import contributors if they exist
    if hasattr(publication_info_schema, 'collection_contributors') and publication_info_schema.collection_contributors:
        import_contributors(publication_info, publication_info_schema)
    
    publication_info.save()
    return publication_info


def create_base_publication_info(publication_info_schema, collection: Collection) -> CollectionPublicationInfo:
    """
    Create and populate the base publication info model.
    
    Args:
        publication_info_schema: The publication info section of the BLAM collection repository schema.
        collection: The Collection instance to attach this publication info to.
        
    Returns:
        A CollectionPublicationInfo instance with basic fields populated.
    """
    # Prepare publication info data
    publication_info_data = {
        'collection': collection  # Set the reference to the collection
    }
    
    # Set the publication year
    if publication_info_schema.collection_publication_year:
        # Handle both string and XmlPeriod types
        year_value = publication_info_schema.collection_publication_year
        if hasattr(year_value, 'value'):
            year_value = year_value.value
        publication_info_data['publication_year'] = int(str(year_value))
    else:
        # Required field, use current year if missing
        from datetime import datetime
        publication_info_data['publication_year'] = datetime.now().year
    
    # Set the data provider
    if publication_info_schema.collection_data_provider:
        publication_info_data['data_provider'] = publication_info_schema.collection_data_provider
    else:
        publication_info_data['data_provider'] = ""  # Required field, use empty string if missing
    
    # Try to find an existing publication info for this collection
    try:
        publication_info = CollectionPublicationInfo.objects.get(
            collection=collection
        )
        
        # Update fields that might have changed
        if 'publication_year' in publication_info_data:
            publication_info.publication_year = publication_info_data['publication_year']
        if 'data_provider' in publication_info_data:
            publication_info.data_provider = publication_info_data['data_provider']
        publication_info.save()
    except CollectionPublicationInfo.DoesNotExist:
        # Create new if it doesn't exist
        publication_info = CollectionPublicationInfo.objects.create(**publication_info_data)
    
    return publication_info


def import_creators(publication_info: CollectionPublicationInfo, publication_info_schema) -> None:
    """
    Import creators from the schema to the publication info model.
    
    This function creates CollectionCreator objects for each creator in the schema
    and associates them with the publication info model.
    
    Args:
        publication_info: The CollectionPublicationInfo instance to add creators to.
        publication_info_schema: The publication info section of the BLAM collection repository schema.
    """
    if publication_info_schema.collection_creators:
        for idx, creator_schema in enumerate(publication_info_schema.collection_creators.collection_creator):
            # Prepare creator data
            creator_data = {}

            # Set name fields
            if creator_schema.creator_name:
                creator_data['family_name'] = creator_schema.creator_name.creator_family_name

                if hasattr(creator_schema.creator_name, 'creator_given_name') and creator_schema.creator_name.creator_given_name:
                    creator_data['given_name'] = creator_schema.creator_name.creator_given_name
                else:
                    creator_data['given_name'] = ""  # Required field, use empty string if missing

            creator = CollectionCreator.objects.create(
                family_name=creator_data['family_name'],
                given_name=creator_data.get('given_name', ''),
            )
            
            # Add affiliations if they exist
            if hasattr(creator_schema, 'creator_affiliation') and creator_schema.creator_affiliation:
                creator.affiliation = creator_schema.creator_affiliation[0] if creator_schema.creator_affiliation else ""
                creator.save()
            
            # Add name identifiers if they exist
            if hasattr(creator_schema, 'creator_name_identifier') and creator_schema.creator_name_identifier:
                for identifier_schema in creator_schema.creator_name_identifier:
                    # Map identifier type from schema to model
                    id_type_mapping = {
                        CreatorNameIdentifierIdentifierType.ORCID: "orcid",
                        CreatorNameIdentifierIdentifierType.ISNI: "isni",
                        CreatorNameIdentifierIdentifierType.EMAIL: "email",
                        CreatorNameIdentifierIdentifierType.OTHER: "other"
                    }
                    id_type = id_type_mapping.get(identifier_schema.identifier_type, "orcid")
                    
                    # Store the identifier in the appropriate field based on type
                    creator.name_identifier = identifier_schema.value
                    creator.name_identifier_type = id_type
                    creator.save()
            
            # Link creator to publication info with per-publication order
            CollectionPublicationInfoCreator.objects.create(
                collectionpublicationinfo=publication_info,
                collectioncreator=creator,
                order=idx,
            )


def import_contributors(publication_info: CollectionPublicationInfo, publication_info_schema) -> None:
    """
    Import contributors from the schema to the publication info model.
    
    This function creates CollectionContributor objects for each contributor in the schema
    and associates them with the publication info model.
    
    Args:
        publication_info: The CollectionPublicationInfo instance to add contributors to.
        publication_info_schema: The publication info section of the BLAM collection repository schema.
    """
    for contributor_schema in publication_info_schema.collection_contributors.collection_contributor:
        # Prepare contributor data
        contributor_data = {}
        
        # Set name fields
        if contributor_schema.contributor_name:
            contributor_data['family_name'] = contributor_schema.contributor_name.contributor_family_name
            
            if hasattr(contributor_schema.contributor_name, 'contributor_given_name') and contributor_schema.contributor_name.contributor_given_name:
                contributor_data['given_name'] = contributor_schema.contributor_name.contributor_given_name
            else:
                contributor_data['given_name'] = ""  # Required field, use empty string if missing
        
        # Set display name (combination of given and family name)
        given_name = contributor_data.get('given_name', '')
        family_name = contributor_data.get('family_name', '')
        display_name = f"{given_name} {family_name}".strip()
        contributor_data['contributor_display_name'] = display_name
        
        contributor = CollectionContributor.objects.create(
            family_name=contributor_data['family_name'],
            given_name=contributor_data.get('given_name', ''),
            contributor_display_name=contributor_data['contributor_display_name'],
        )
        
        # Add role if it exists
        if hasattr(contributor_schema, 'contributor_role') and contributor_schema.contributor_role:
            contributor.role = contributor_schema.contributor_role
            contributor.save()
        
        # Add affiliations if they exist
        if hasattr(contributor_schema, 'contributor_affiliation') and contributor_schema.contributor_affiliation:
            contributor.affiliation = contributor_schema.contributor_affiliation[0] if contributor_schema.contributor_affiliation else ""
            contributor.save()
        
        # Add name identifiers if they exist
        if hasattr(contributor_schema, 'contributor_name_identifier') and contributor_schema.contributor_name_identifier:
            for identifier_schema in contributor_schema.contributor_name_identifier:
                # Map identifier type from schema to model
                id_type_mapping = {
                    ContributorNameIdentifierIdentifierType.ORCID: "orcid",
                    ContributorNameIdentifierIdentifierType.ISNI: "isni",
                    ContributorNameIdentifierIdentifierType.EMAIL: "email",
                    ContributorNameIdentifierIdentifierType.OTHER: "other"
                }
                id_type = id_type_mapping.get(identifier_schema.identifier_type, "orcid")
                
                # Store the identifier in the appropriate field based on type
                contributor.name_identifier = identifier_schema.value
                contributor.name_identifier_type = id_type
                contributor.save()
        
        # Add the contributor to the publication info
        publication_info.contributors.add(contributor)
