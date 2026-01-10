from typing import Dict, Any, List, Optional
from django.db.models import QuerySet
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleStructuralInfo,
    BundleAdditionalMetadataFile,
    BundleResources
)
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd,
    BundleIsMemberOfCollectionIdentifierType
)

# Type aliases for nested classes from the schema
BundleStructuralInfoType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo
BundleResourcesType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources
MediaResourceType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.MediaResource
WrittenResourceType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.WrittenResource
OtherResourceType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.OtherResource
BundleAdditionalMetadataFileType = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleAdditionalMetadataFile


def export_structural_info(structural_info: BundleStructuralInfo, cmd_data: Cmd) -> None:
    """
    Export bundle structural information from Django models to BLAM schema.
    
    Args:
        structural_info: The BundleStructuralInfo instance to export
        cmd_data: The BLAM bundle repository schema data to populate
    """
    # Create the bundle structural info structure
    bundle_info = BundleStructuralInfoType()
    
    collection = structural_info.is_member_of_collection
    if collection:
        collection_info = collection.get_general_info
        if collection_info:
            bundle_info.bundle_is_member_of_collection = create_collection_membership(collection_info)
    
    # Export additional metadata files if present
    if structural_info.additional_metadata_files.exists():
        bundle_info.bundle_additional_metadata_file = [
            export_additional_metadata_file(file) 
            for file in structural_info.additional_metadata_files.all()
        ]
    
    # Export resources
    bundle_info.bundle_resources = export_bundle_resources(structural_info)
    
    # Assign to cmd_data
    cmd_data.components.blam_bundle_repository_v1_0.bundle_structural_info = bundle_info


def create_collection_membership(collection_info: Any) -> Any:
    """
    Create a collection membership object from the model.
    
    Args:
        collection_info: The CollectionGeneralInfo instance
        
    Returns:
        A collection membership object for the schema
    """
    membership = Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleIsMemberOfCollection()
    membership.value = collection_info.id_value
    membership.identifier_type = map_to_collection_identifier_type(collection_info.id_type)
    return membership


def map_to_collection_identifier_type(id_type: str) -> BundleIsMemberOfCollectionIdentifierType:
    """
    Map model identifier type to schema enum.
    
    Args:
        id_type: The identifier type from the model
        
    Returns:
        The corresponding schema identifier type enum value
    """
    mapping = {
        "DOI": BundleIsMemberOfCollectionIdentifierType.DOI,
        "HANDLE": BundleIsMemberOfCollectionIdentifierType.HANDLE,
    }
    return mapping.get(id_type, BundleIsMemberOfCollectionIdentifierType.DOI)


def export_additional_metadata_file(file: BundleAdditionalMetadataFile) -> BundleAdditionalMetadataFileType:
    """
    Export an additional metadata file to schema format.
    
    Args:
        file: The additional metadata file instance
        
    Returns:
        An additional metadata file object for the schema
    """
    metadata_file = BundleAdditionalMetadataFileType()
    metadata_file.file_name = file.file_name
    metadata_file.file_pid = file.file_pid
    metadata_file.mime_type = file.mime_type
    metadata_file.is_metadata_for = file.is_metadata_for
    
    if file.file_description:
        metadata_file.file_description = file.file_description
    
    return metadata_file


def export_bundle_resources(structural_info: BundleStructuralInfo) -> BundleResourcesType:
    """
    Export bundle resources to schema format.
    
    Args:
        structural_info: The BundleStructuralInfo instance
        
    Returns:
        A bundle resources container for the schema
    """
    resources_data = BundleResourcesType()

    bundle_resources = BundleResources.objects.filter(bundle=structural_info.bundle).first()
    if not bundle_resources:
        return resources_data

    if bundle_resources.bundle_media_resources.exists():
        resources_data.media_resource = [
            export_media_resource(resource) for resource in bundle_resources.bundle_media_resources.all()
        ]

    if bundle_resources.bundle_written_resources.exists():
        resources_data.written_resource = [
            export_written_resource(resource) for resource in bundle_resources.bundle_written_resources.all()
        ]

    if bundle_resources.bundle_other_resources.exists():
        resources_data.other_resource = [
            export_other_resource(resource) for resource in bundle_resources.bundle_other_resources.all()
        ]

    return resources_data


def export_media_resource(resource: Any) -> MediaResourceType:
    """
    Export a media resource to schema format.
    
    Args:
        resource: The media resource instance
        
    Returns:
        A media resource object for the schema
    """
    resource_data = MediaResourceType()
    
    # Set required fields
    resource_data.file_name = resource.file_name
    resource_data.file_pid = resource.file_pid
    resource_data.mime_type = resource.mime_type
    resource_data.file_length = resource.file_length
    
    # Set optional fields
    if hasattr(resource, 'file_description') and resource.file_description:
        resource_data.file_description = resource.file_description
    
    return resource_data


def export_written_resource(resource: Any) -> WrittenResourceType:
    """
    Export a written resource to schema format.
    
    Args:
        resource: The written resource instance
        
    Returns:
        A written resource object for the schema
    """
    resource_data = WrittenResourceType()
    
    # Set required fields
    resource_data.file_name = resource.file_name
    resource_data.file_pid = resource.file_pid
    resource_data.mime_type = resource.mime_type
    
    # Set optional fields
    if hasattr(resource, 'file_description') and resource.file_description:
        resource_data.file_description = resource.file_description
    
    # Set annotation references if present
    if hasattr(resource, 'annotations') and resource.annotations.exists():
        resource_data.is_annotation_of = [
            annotation.reference for annotation in resource.annotations.all()
        ]
    
    return resource_data


def export_other_resource(resource: Any) -> OtherResourceType:
    """
    Export an other resource to schema format.
    
    Args:
        resource: The other resource instance
        
    Returns:
        An other resource object for the schema
    """
    resource_data = OtherResourceType()
    
    # Set required fields
    resource_data.file_name = resource.file_name
    resource_data.file_pid = resource.file_pid
    resource_data.mime_type = resource.mime_type
    
    # Set optional fields
    if hasattr(resource, 'file_description') and resource.file_description:
        resource_data.file_description = resource.file_description
    
    return resource_data
