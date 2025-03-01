from django.db import transaction
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
    CollectionAdditionalMetadataFile,
    CollectionMembers,
    CollectionHasCollectionMember
)
from blam_schemas.collection.blam_collection_repository_v1_0 import (
    Cmd,
    CollectionHasCollectionMemberIdentifierType
)


@transaction.atomic
def import_structural_info(collection_schema: Cmd) -> CollectionStructuralInfo:
    """
    Import structural info from a BLAM collection repository schema to Django models.
    
    This function extracts structural metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    additional metadata files and collection members.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        collection_schema: The BLAM collection repository schema containing structural info.
        
    Returns:
        A fully populated CollectionStructuralInfo instance with all related objects.
    """
    # Extract the structural info section from the schema
    structural_info_schema = collection_schema.components.blam_collection_repository_v1_0.collection_structural_info
    
    # Create and populate the structural info model
    structural_info = CollectionStructuralInfo.objects.create()
    
    # Import additional metadata files if they exist
    if hasattr(structural_info_schema, 'collection_additional_metadata_file') and structural_info_schema.collection_additional_metadata_file:
        import_additional_metadata_files(structural_info, structural_info_schema)
    
    # Import collection members
    if hasattr(structural_info_schema, 'collection_members') and structural_info_schema.collection_members:
        import_collection_members(structural_info, structural_info_schema.collection_members)
    
    structural_info.save()
    return structural_info


def import_additional_metadata_files(structural_info: CollectionStructuralInfo, structural_info_schema) -> None:
    """
    Import additional metadata files from the schema to the structural info model.
    
    This function creates CollectionAdditionalMetadataFile objects for each metadata file
    in the schema and associates them with the structural info model.
    
    Args:
        structural_info: The CollectionStructuralInfo instance to add metadata files to.
        structural_info_schema: The structural info section of the BLAM collection repository schema.
    """
    for metadata_file_schema in structural_info_schema.collection_additional_metadata_file:
        # Prepare metadata file data
        metadata_file_data = {
            'file_name': metadata_file_schema.file_name,
            'file_pid': metadata_file_schema.file_pid,
            'mime_type': metadata_file_schema.mime_type,
            'is_metadata_for': metadata_file_schema.is_metadata_for
        }
        
        # Set optional fields if they exist
        if hasattr(metadata_file_schema, 'file_description') and metadata_file_schema.file_description:
            metadata_file_data['file_description'] = metadata_file_schema.file_description
        
        # Try to find an existing metadata file with the same PID, or create a new one
        metadata_file, created = CollectionAdditionalMetadataFile.objects.get_or_create(
            file_pid=metadata_file_data['file_pid'],
            defaults=metadata_file_data
        )
        
        # Update fields that might have changed
        if not created:
            for key, value in metadata_file_data.items():
                setattr(metadata_file, key, value)
            metadata_file.save()
        
        # Add the metadata file to the structural info
        structural_info.additional_metadata_files.add(metadata_file)


def import_collection_members(structural_info: CollectionStructuralInfo, collection_members_schema) -> None:
    """
    Import collection members from the schema to the structural info model.
    
    This function creates a CollectionMembers object and associated CollectionHasCollectionMember
    objects for each member in the schema and associates them with the structural info model.
    
    Args:
        structural_info: The CollectionStructuralInfo instance to add members to.
        collection_members_schema: The collection members section of the structural info schema.
    """
    # Create a collection members container
    collection_members = CollectionMembers.objects.create()
    
    # Process each member reference
    for i, member_schema in enumerate(collection_members_schema.collection_has_collection_member):
        # Map identifier type from schema to model
        id_type_mapping = {
            CollectionHasCollectionMemberIdentifierType.DOI: "doi",
            CollectionHasCollectionMemberIdentifierType.HANDLE: "handle"
        }
        id_type = id_type_mapping.get(member_schema.identifier_type, "handle")
        
        # Create the member reference
        member = CollectionHasCollectionMember.objects.create(
            collection_members=collection_members,
            member_uri=member_schema.value,
            identifier_type=id_type,
            order=i  # Use the index as the order
        )
    
    # Add the collection members to the structural info
    structural_info.collection_members.add(collection_members)
