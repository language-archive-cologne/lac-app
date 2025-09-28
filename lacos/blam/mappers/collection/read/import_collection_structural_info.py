from typing import Any
from django.db import transaction
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
    CollectionAdditionalMetadataFile
)
from lacos.blam.models.collection.collection_repository import Collection


@transaction.atomic
def import_structural_info(cmd_data: Any, collection: Collection) -> CollectionStructuralInfo:
    """
    Import structural info from a BLAM collection repository schema to Django models.
    
    This function extracts structural metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    additional metadata files.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        cmd_data: The parsed BLAM collection data containing structural info.
        collection: The Collection instance to attach this structural info to.
        
    Returns:
        A fully populated CollectionStructuralInfo instance with all related objects.
    """
    # Extract the structural info section from the schema
    structural_info_schema = cmd_data.components.blam_collection_repository_v1_0.collection_structural_info
    
    # Try to find an existing structural info for this collection or create a new one
    try:
        structural_info = CollectionStructuralInfo.objects.get(collection=collection)
        # Clear existing additional metadata files to avoid duplicates
        structural_info.additional_metadata_files.clear()
    except CollectionStructuralInfo.DoesNotExist:
        # Create the structural info model with reference to collection
        structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    
    # Import additional metadata files if they exist
    if hasattr(structural_info_schema, 'collection_additional_metadata_file') and structural_info_schema.collection_additional_metadata_file:
        import_additional_metadata_files(structural_info, structural_info_schema)
    
    return structural_info


def import_additional_metadata_files(structural_info: CollectionStructuralInfo, structural_info_schema) -> None:
    """
    Import additional metadata files from the schema to the structural info model.
    
    This function creates CollectionAdditionalMetadataFile objects for each metadata file
    in the schema and associates them with the structural info model through a many-to-many
    relationship.
    
    Args:
        structural_info: The CollectionStructuralInfo instance to add metadata files to.
        structural_info_schema: The structural info section of the BLAM collection repository schema.
    """
    for metadata_file_schema in structural_info_schema.collection_additional_metadata_file:
        # Create the metadata file
        metadata_file = CollectionAdditionalMetadataFile.objects.create(
            file_name=metadata_file_schema.file_name,
            file_pid=metadata_file_schema.file_pid,
            mime_type=metadata_file_schema.mime_type,
            is_metadata_for=metadata_file_schema.is_metadata_for,
            file_description=getattr(metadata_file_schema, 'file_description', None)
        )
        # Add it to the structural info's many-to-many relationship
        structural_info.additional_metadata_files.add(metadata_file)
