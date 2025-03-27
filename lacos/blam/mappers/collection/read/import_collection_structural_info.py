from django.db import transaction
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
    CollectionAdditionalMetadataFile
)
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd


@transaction.atomic
def import_structural_info(collection_schema: Cmd) -> CollectionStructuralInfo:
    """
    Import structural info from a BLAM collection repository schema to Django models.
    
    This function extracts structural metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    additional metadata files.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        collection_schema: The BLAM collection repository schema containing structural info.
        
    Returns:
        A fully populated CollectionStructuralInfo instance with all related objects.
    """
    # Extract the structural info section from the schema
    structural_info_schema = collection_schema.components.blam_collection_repository_v1_0.collection_structural_info
    
    # Create the structural info model
    structural_info = CollectionStructuralInfo.objects.create()
    
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
