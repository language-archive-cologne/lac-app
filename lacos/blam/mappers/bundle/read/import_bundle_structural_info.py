from typing import Optional, List, Tuple
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleAdditionalMetadataFile,
    BundleResources,
    MediaResource,
    WrittenResource,
    WrittenResourceAnnotation,
    OtherResource
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd, BundleIsMemberOfCollectionIdentifierType
)
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices


@transaction.atomic
def import_structural_info(cmd_data: Cmd, collection_identifier: str, identifier_type: str) -> Optional[BundleStructuralInfo]:
    """
    Import structural info from CMD object to Django models.
    
    Args:
        cmd_data: The CMD object containing bundle structural information
        collection_identifier: The identifier value (e.g., DOI, Handle) of the collection
        identifier_type: The type of identifier (e.g., "DOI", "Handle")
        
    Returns:
        BundleStructuralInfo object or None if structural info is missing
    """
    components = cmd_data.components
    if not components or not components.blam_bundle_repository_v1_0:
        return None
        
    repo = components.blam_bundle_repository_v1_0
    struct_info = repo.bundle_structural_info
    if not struct_info:
        return None
    
    # Verify collection exists
    try:
        collection_general_info = CollectionGeneralInfo.objects.get(
            id_value=collection_identifier,
            id_type=identifier_type
        )
        collection = Collection.objects.get(general_info=collection_general_info)
    except ObjectDoesNotExist:
        raise ValueError(f"Collection with identifier {collection_identifier} ({identifier_type}) does not exist")
    
    # Create structural info first
    bundle_struct_info, created = BundleStructuralInfo.objects.get_or_create(
        is_member_of_collection=collection
    )
    
    # Import optional components only if they exist
    if struct_info.bundle_additional_metadata_file:
        import_additional_metadata_files(bundle_struct_info, struct_info.bundle_additional_metadata_file)
    
    if struct_info.bundle_resources:
        import_bundle_resources(bundle_struct_info, struct_info.bundle_resources)
    
    return bundle_struct_info


def import_additional_metadata_files(
    bundle_struct_info: BundleStructuralInfo, 
    metadata_files_data: List
) -> None:
    """
    Import additional metadata files from CMD data to Django models.
    
    Args:
        bundle_struct_info: The BundleStructuralInfo object to link files to
        metadata_files_data: List of metadata file data from the CMD object
    """
    for metadata_file_data in metadata_files_data:
        # Use file_pid as unique identifier
        metadata_file, created = BundleAdditionalMetadataFile.objects.get_or_create(
            file_pid=metadata_file_data.file_pid,
            defaults={
                'file_name': metadata_file_data.file_name,
                'mime_type': metadata_file_data.mime_type,
                'is_metadata_for': metadata_file_data.is_metadata_for,
                'file_description': metadata_file_data.file_description
            }
        )
        
        # Update fields if the record already exists
        if not created:
            metadata_file.file_name = metadata_file_data.file_name
            metadata_file.mime_type = metadata_file_data.mime_type
            metadata_file.is_metadata_for = metadata_file_data.is_metadata_for
            metadata_file.file_description = metadata_file_data.file_description
            metadata_file.save()
            
        bundle_struct_info.additional_metadata_files.add(metadata_file)


def import_bundle_resources(
    bundle_struct_info: BundleStructuralInfo,
    resources_data # This is the parsed XML data for <BundleResources>
) -> None:
    """
    Import bundle resources from CMD data to Django models.
    
    Args:
        bundle_struct_info: The BundleStructuralInfo object to link resources to
        resources_data: Resources data from the CMD object (nested within struct info)
    """
    # Get or create the associated BundleResources instance via the relationship
    if bundle_struct_info.resources is None:
        bundle_resources = BundleResources.objects.create() # Create a new one
        bundle_struct_info.resources = bundle_resources    # Assign it
        bundle_struct_info.save(update_fields=['resources']) # Save just the link
    else:
        bundle_resources = bundle_struct_info.resources # Use the existing one

    # Ensure resources_data is not None before accessing attributes
    if not resources_data:
        return # If no <BundleResources> in XML, nothing more to do

    # Import media resources if present in XML data
    if resources_data.media_resource:
        import_media_resources(bundle_resources, resources_data.media_resource)

    # Import written resources if present in XML data
    if resources_data.written_resource:
        import_written_resources(bundle_resources, resources_data.written_resource)

    # Import other resources if present in XML data
    if resources_data.other_resource:
        import_other_resources(bundle_resources, resources_data.other_resource)


def import_media_resources(
    bundle_resources: BundleResources, 
    media_resources_data: List
) -> None:
    """
    Import media resources from CMD data to Django models.
    
    Args:
        bundle_resources: The BundleResources object to link media resources to
        media_resources_data: List of media resource data from the CMD object
    """
    for media_resource_data in media_resources_data:
        # Use file_pid as unique identifier
        media_resource, created = MediaResource.objects.get_or_create(
            file_pid=media_resource_data.file_pid,
            defaults={
                'file_name': media_resource_data.file_name,
                'mime_type': media_resource_data.mime_type,
                'file_length': media_resource_data.file_length,
                'file_description': media_resource_data.file_description
            }
        )
        
        # Update fields if the record already exists
        if not created:
            media_resource.file_name = media_resource_data.file_name
            media_resource.mime_type = media_resource_data.mime_type
            media_resource.file_length = media_resource_data.file_length
            media_resource.file_description = media_resource_data.file_description
            media_resource.save()
            
        bundle_resources.bundle_media_resources.add(media_resource)


def import_written_resources(
    bundle_resources: BundleResources, 
    written_resources_data: List
) -> None:
    """
    Import written resources from CMD data to Django models.
    
    Args:
        bundle_resources: The BundleResources object to link written resources to
        written_resources_data: List of written resource data from the CMD object
    """
    for written_resource_data in written_resources_data:
        # Use file_pid as unique identifier
        written_resource, created = WrittenResource.objects.get_or_create(
            file_pid=written_resource_data.file_pid,
            defaults={
                'file_name': written_resource_data.file_name,
                'mime_type': written_resource_data.mime_type,
                'file_description': written_resource_data.file_description
            }
        )
        
        # Update fields if the record already exists
        if not created:
            written_resource.file_name = written_resource_data.file_name
            written_resource.mime_type = written_resource_data.mime_type
            written_resource.file_description = written_resource_data.file_description
            written_resource.save()
        
        # Handle annotations
        if written_resource_data.is_annotation_of:
            for annotation_target in written_resource_data.is_annotation_of:
                # Use written_resource and is_annotation_of as unique identifiers
                annotation, created = WrittenResourceAnnotation.objects.get_or_create(
                    written_resource=written_resource,
                    is_annotation_of=annotation_target
                )
        
        bundle_resources.bundle_written_resources.add(written_resource)


def import_other_resources(
    bundle_resources: BundleResources, 
    other_resources_data: List
) -> None:
    """
    Import other resources from CMD data to Django models.
    
    Args:
        bundle_resources: The BundleResources object to link other resources to
        other_resources_data: List of other resource data from the CMD object
    """
    for other_resource_data in other_resources_data:
        # Use file_pid as unique identifier
        other_resource, created = OtherResource.objects.get_or_create(
            file_pid=other_resource_data.file_pid,
            defaults={
                'file_name': other_resource_data.file_name,
                'mime_type': other_resource_data.mime_type,
                'file_description': other_resource_data.file_description
            }
        )
        
        # Update fields if the record already exists
        if not created:
            other_resource.file_name = other_resource_data.file_name
            other_resource.mime_type = other_resource_data.mime_type
            other_resource.file_description = other_resource_data.file_description
            other_resource.save()
            
        bundle_resources.bundle_other_resources.add(other_resource)
