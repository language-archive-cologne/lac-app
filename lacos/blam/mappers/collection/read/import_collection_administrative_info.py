from typing import Any
from django.db import transaction
from django.utils.dateparse import parse_date
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionIdenticalResource,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.mappers.collection.read.import_collection_license import create_collection_license


@transaction.atomic
def import_administrative_info(cmd_data: Any, collection: Collection) -> CollectionAdministrativeInfo:
    """
    Import administrative info from a BLAM collection repository schema to a Django model.
    
    This function extracts administrative metadata from the BLAM collection repository schema
    and converts it to a Django model representation, including related models for
    identical resources, licenses, and rights holders.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        cmd_data: The parsed BLAM collection data containing administrative info.
        collection: The Collection instance to attach this administrative info to.
        
    Returns:
        A fully populated CollectionAdministrativeInfo instance with all related objects.
    """
    # Extract the administrative info section from the schema
    admin_info_schema = cmd_data.components.blam_collection_repository_v1_0.collection_administrative_info
    
    # Create and populate the administrative info model with reference to collection
    admin_info = create_base_administrative_info(admin_info_schema, collection)
    
    # Import related objects
    import_identical_resources(admin_info, admin_info_schema)
    import_licenses(admin_info, admin_info_schema)
    import_rights_holders(admin_info, admin_info_schema)
    
    admin_info.save()
    return admin_info


def create_base_administrative_info(admin_info_schema, collection: Collection) -> CollectionAdministrativeInfo:
    """
    Create and populate the base administrative info model.
    
    Args:
        admin_info_schema: The administrative info section of the BLAM collection repository schema.
        collection: The Collection instance to attach this administrative info to.
        
    Returns:
        A CollectionAdministrativeInfo instance with basic fields populated.
    """
    # Prepare administrative info data
    admin_info_data = {
        'collection': collection  # Set the reference to the collection
    }
    
    # Set the availability date
    if admin_info_schema.availability_date:
        date_obj = admin_info_schema.availability_date
        admin_info_data['availability_date'] = f"{date_obj.year}-{date_obj.month:02d}-{date_obj.day:02d}"
    
    # Set the derivation URI if it exists
    if admin_info_schema.collection_is_derivation_of:
        admin_info_data['is_derivation_of'] = admin_info_schema.collection_is_derivation_of
    
    # Get or create administrative info using collection and availability_date as unique fields
    # Try to find an existing administrative info for this collection
    try:
        admin_info = CollectionAdministrativeInfo.objects.get(
            collection=collection
        )
        
        # Update fields if it exists
        if 'availability_date' in admin_info_data:
            admin_info.availability_date = admin_info_data['availability_date']
        if 'is_derivation_of' in admin_info_data:
            admin_info.is_derivation_of = admin_info_data['is_derivation_of']
        admin_info.save()
    except CollectionAdministrativeInfo.DoesNotExist:
        # Create new if it doesn't exist
        admin_info = CollectionAdministrativeInfo.objects.create(**admin_info_data)
    
    return admin_info


def import_identical_resources(admin_info: CollectionAdministrativeInfo, admin_info_schema) -> None:
    """
    Import identical resources from the schema to the administrative info model.
    
    Args:
        admin_info: The CollectionAdministrativeInfo instance to add identical resources to.
        admin_info_schema: The administrative info section of the BLAM collection repository schema.
    """
    for identical_resource_uri in admin_info_schema.collection_is_identical_to:
        # Skip empty URIs
        if identical_resource_uri and identical_resource_uri.strip():
            identical_resource, created = CollectionIdenticalResource.objects.get_or_create(
                uri=identical_resource_uri
            )
            admin_info.is_identical_to.add(identical_resource)


def import_licenses(admin_info: CollectionAdministrativeInfo, admin_info_schema) -> None:
    """
    Import licenses from the schema to the administrative info model.
    
    This function creates CollectionLicense objects for each license in the schema
    and associates them with the administrative info model.
    
    Args:
        admin_info: The CollectionAdministrativeInfo instance to add licenses to.
        admin_info_schema: The administrative info section of the BLAM collection repository schema.
    """
    # Clear existing licenses to avoid duplicates
    admin_info.licenses.clear()
    
    # Skip if no licenses
    if not hasattr(admin_info_schema, 'license') or not admin_info_schema.license:
        return
    
    # Create and add each license
    for license_schema in admin_info_schema.license:
        license_model = create_collection_license(admin_info_schema, license_schema)
        if license_model:  # Only add if valid license was created
            admin_info.licenses.add(license_model)


def import_rights_holders(admin_info: CollectionAdministrativeInfo, admin_info_schema) -> None:
    """
    Import rights holders from the schema to the administrative info model.
    
    This function creates CollectionRightsHolder objects for each rights holder in the schema
    and associates them with the administrative info model. It also imports the rights
    holder identifiers for each rights holder.
    
    Args:
        admin_info: The CollectionAdministrativeInfo instance to add rights holders to.
        admin_info_schema: The administrative info section of the BLAM collection repository schema.
    """
    for rights_holder_schema in admin_info_schema.rights_holder:
        rights_holder, created = CollectionRightsHolder.objects.get_or_create(
            rights_holder_name=rights_holder_schema.rights_holder_name
        )
        
        # Import rights holder identifiers
        for identifier_schema in rights_holder_schema.rights_holder_identifier:
            # Handle potentially missing identifier type
            # Use "OTHER" as default when identifier_type is missing
            id_type_value = "OTHER"
            if identifier_schema.identifier_type:
                 id_type_value = identifier_schema.identifier_type.value

            identifier, created = CollectionRightsHolderIdentifier.objects.get_or_create(
                identifier=identifier_schema.value or "", # Use empty string if value is None/empty
                identifier_type=id_type_value # Use "OTHER" if type is missing
            )
            rights_holder.rights_holder_identifiers.add(identifier)
        
        admin_info.rights_holders.add(rights_holder)
