from django.db import transaction
from typing import Any, Optional, Tuple
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd, SimpletypeAccess41
from lacos.blam.models.collection.collection_administrative_info import CollectionLicense


@transaction.atomic
def import_collection_license(cmd_data: Cmd) -> Tuple[str, Optional[str]]:
    """
    Import collection license information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM collection repository schema data
        
    Returns:
        A tuple containing the license value and license URI
    """
    # Get the repository component
    repo = cmd_data.components.blam_collection_repository_v1_0
    
    # Extract license information
    license_value, license_uri = extract_license_info(repo)
    
    return license_value, license_uri


def extract_license_info(repo: Any) -> Tuple[str, Optional[str]]:
    """
    Extract license information from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        A tuple containing the license value and license URI
    """
    # Extract license value
    license_value = extract_license_value(repo)
    
    # Extract license URI
    license_uri = extract_license_uri(repo)
    
    return license_value, license_uri


def extract_license_value(repo: Any) -> str:
    """
    Extract the license value from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        The license value as a string
    """
    if hasattr(repo, 'collection_administrative_info') and repo.collection_administrative_info:
        admin_info = repo.collection_administrative_info
        if hasattr(admin_info, 'license') and admin_info.license:
            # Get the first license entry
            license_entry = admin_info.license[0]
            if hasattr(license_entry, 'license_name'):
                return license_entry.license_name
    return ""


def extract_license_uri(repo: Any) -> Optional[str]:
    """
    Extract the license URI from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        The license URI as a string or None
    """
    if hasattr(repo, 'collection_administrative_info') and repo.collection_administrative_info:
        admin_info = repo.collection_administrative_info
        if hasattr(admin_info, 'license') and admin_info.license:
            # Get the first license entry
            license_entry = admin_info.license[0]
            if hasattr(license_entry, 'license_identifier'):
                return license_entry.license_identifier
    return None


def create_collection_license(admin_info_schema, license_schema=None) -> Optional[CollectionLicense]:
    """
    Create a CollectionLicense model instance from the schema data.
    
    Args:
        admin_info_schema: The administrative info section of the BLAM collection repository schema.
        license_schema: Optional specific license schema to use. If not provided, uses the first license.
        
    Returns:
        A CollectionLicense instance or None if no valid license data.
    """
    # Map access type from schema to model
    access = "open"  # Default value
    if admin_info_schema.access and admin_info_schema.access.value:
        access_mapping = {
            SimpletypeAccess41.OPEN: "open",
            SimpletypeAccess41.REGISTRATION_REQUIRED: "registration_required",
            SimpletypeAccess41.REQUEST_REQUIRED: "request_required"
        }
        access = access_mapping.get(admin_info_schema.access.value, "open")
    
    # Use provided license schema or get first one
    license_data = license_schema or (admin_info_schema.license[0] if admin_info_schema.license else None)
    
    # Return None if no valid license data
    if not license_data:
        return None
    
    # Convert None to empty string for required fields
    license_name = "" if license_data.license_name is None else str(license_data.license_name)
    license_identifier = "" if license_data.license_identifier is None else str(license_data.license_identifier)
    
    # Get or create the license
    license_model, created = CollectionLicense.objects.get_or_create(
        license_name=license_name,
        license_identifier=license_identifier,
        defaults={'access': access}
    )
    
    # Update access if the license already existed
    if not created:
        license_model.access = access
        license_model.save()
    
    return license_model 