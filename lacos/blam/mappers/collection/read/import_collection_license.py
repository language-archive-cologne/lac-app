from typing import Any, Optional, Tuple
from django.db import transaction
from django.utils import timezone
from blam_schemas.collection import SimpletypeAccess41
from lacos.blam.models.collection.collection_administrative_info import CollectionLicense, CollectionAdministrativeInfo
from lacos.blam.models.collection.collection_repository import Collection


@transaction.atomic
def import_collection_license(cmd_data: Any, collection: Collection) -> Optional[CollectionLicense]:
    """
    Import collection license information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM collection repository schema data
        collection: The Collection instance to attach the license to
        
    Returns:
        The created CollectionLicense instance or None if no license data is found
    """
    # Get the repository component
    repo = cmd_data.components.blam_collection_repository_v1_2
    
    # If there's no administrative info, return None
    if not hasattr(repo, 'collection_administrative_info') or not repo.collection_administrative_info:
        return None
    
    admin_info_schema = repo.collection_administrative_info
    
    # Extract availability date from schema - XmlDate needs to be converted to ISO format string
    if not hasattr(admin_info_schema, 'availability_date') or not admin_info_schema.availability_date:
        # Use a reasonable default date for tests if not available in schema
        availability_date = timezone.now().date().isoformat()
    else:
        # Convert XmlDate to ISO format string that Django can parse
        xml_date = admin_info_schema.availability_date
        availability_date = f"{xml_date.year}-{xml_date.month:02d}-{xml_date.day:02d}"
    
    # Get or create the administrative info for this collection
    try:
        admin_info = CollectionAdministrativeInfo.objects.get(collection=collection)
    except CollectionAdministrativeInfo.DoesNotExist:
        # Create admin info with the extracted availability date
        admin_info = CollectionAdministrativeInfo.objects.create(
            collection=collection,
            availability_date=availability_date
        )
    
    # If there's no license information, return None
    if not hasattr(admin_info_schema, 'license') or not admin_info_schema.license:
        return None
    
    # Create the CollectionLicense from the first license in the schema
    license_schema = admin_info_schema.license[0]
    license_model = create_collection_license(admin_info_schema, license_schema)
    
    # Associate the license with the admin_info if it was created
    if license_model:
        admin_info.licenses.add(license_model)
    
    return license_model


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
    # Map access type from schema to model (v1.2 uses public/academic/restricted)
    access = "public"  # Default value
    if admin_info_schema.access and admin_info_schema.access.value:
        access_mapping = {
            SimpletypeAccess41.PUBLIC: "public",
            SimpletypeAccess41.ACADEMIC: "academic",
            SimpletypeAccess41.RESTRICTED: "restricted"
        }
        access = access_mapping.get(admin_info_schema.access.value, "public")
    
    # Use provided license schema or get first one
    license_data = license_schema or (admin_info_schema.license[0] if admin_info_schema.license else None)
    
    # Return None if no valid license data
    if not license_data:
        return None
    
    # Convert None to empty string for required fields
    license_name = "" if license_data.license_name is None else str(license_data.license_name)
    license_identifier = "" if getattr(license_data, 'license_identifier', None) is None else str(license_data.license_identifier)
    
    # Get or create the license
    license_model, created = CollectionLicense.objects.get_or_create(
        license_name=license_name,
        license_identifier=license_identifier,
        defaults={'access': access}
    )
    
    # Update access if needed
    if not created and license_model.access != access:
        license_model.access = access
        license_model.save()
    
    return license_model 
