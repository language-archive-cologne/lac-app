from django.db import transaction
from django.utils.dateparse import parse_date
from lacos.blam.mappers.import_cleanup import (
    delete_unreferenced_records,
    detach_parent_m2m_children,
)
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo,
    BundleIdenticalResource,
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier
)
from blam_schemas.bundle import Cmd, SimpletypeAccess51


@transaction.atomic
def import_administrative_info(bundle_schema: Cmd, bundle: 'Bundle') -> BundleAdministrativeInfo:
    """
    Import administrative info from a BLAM bundle repository schema to a Django model.
    
    This function extracts administrative metadata from the BLAM bundle repository schema
    and converts it to a Django model representation, including related models for
    identical resources, licenses, and rights holders.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        bundle_schema: The BLAM bundle repository schema containing administrative info.
        bundle: The Bundle instance to associate the administrative info with.
        
    Returns:
        A fully populated BundleAdministrativeInfo instance with all related objects.
    """
    # Extract the administrative info section from the schema
    admin_info_schema = bundle_schema.components.blam_bundle_repository_v1_1.bundle_administrative_info
    
    # Format the date for lookup
    date_str = None
    if admin_info_schema.availability_date:
        date_str = f"{admin_info_schema.availability_date.year}-{admin_info_schema.availability_date.month:02d}-{admin_info_schema.availability_date.day:02d}"

    admin_info = BundleAdministrativeInfo.objects.filter(bundle=bundle).first()

    if admin_info:
        if date_str:
            admin_info.availability_date = date_str
        if admin_info_schema.bundle_is_derivation_of:
            admin_info.is_derivation_of = admin_info_schema.bundle_is_derivation_of
        admin_info.save()
    else:
        # Create and populate the administrative info model
        admin_info = create_base_administrative_info(admin_info_schema, bundle)

    old_rights_holder_identifier_ids = list(
        admin_info.rights_holders.values_list(
            "rights_holder_identifiers__id",
            flat=True,
        ).distinct()
    )
    detach_parent_m2m_children(admin_info, "is_identical_to")
    detach_parent_m2m_children(admin_info, "licenses")
    detach_parent_m2m_children(admin_info, "rights_holders")
    delete_unreferenced_records(
        BundleRightsHolderIdentifier,
        old_rights_holder_identifier_ids,
        ["rights_holders_identifiers"],
    )

    # Import related objects
    import_identical_resources(admin_info, admin_info_schema)
    import_licenses(admin_info, admin_info_schema)
    import_rights_holders(admin_info, admin_info_schema)

    return admin_info


def create_base_administrative_info(admin_info_schema, bundle: 'Bundle') -> BundleAdministrativeInfo:
    """
    Create and populate the base administrative info model.
    
    Args:
        admin_info_schema: The administrative info section of the BLAM bundle repository schema.
        bundle: The Bundle instance to associate the administrative info with.
        
    Returns:
        A BundleAdministrativeInfo instance with basic fields populated.
    """
    admin_info = BundleAdministrativeInfo()
    
    # Set the availability date (XmlDate doesn't have .value attribute)
    if admin_info_schema.availability_date:
        # Convert XmlDate to string in ISO format without timezone
        date_str = f"{admin_info_schema.availability_date.year}-{admin_info_schema.availability_date.month:02d}-{admin_info_schema.availability_date.day:02d}"
        admin_info.availability_date = date_str
    
    # Set the derivation URI if it exists
    if admin_info_schema.bundle_is_derivation_of:
        admin_info.is_derivation_of = admin_info_schema.bundle_is_derivation_of
    
    # Set the bundle reference
    admin_info.bundle = bundle
    
    # Save the model to get an ID for many-to-many relationships
    admin_info.save()
    
    return admin_info


def import_identical_resources(admin_info: BundleAdministrativeInfo, admin_info_schema) -> None:
    """
    Import identical resources from the schema to the administrative info model.
    
    Args:
        admin_info: The BundleAdministrativeInfo instance to add identical resources to.
        admin_info_schema: The administrative info section of the BLAM bundle repository schema.
    """
    for identical_resource_uri in admin_info_schema.bundle_is_identical_to:
        identical_resource = BundleIdenticalResource.objects.create(
            uri=identical_resource_uri
        )
        admin_info.is_identical_to.add(identical_resource)


def import_licenses(admin_info: BundleAdministrativeInfo, admin_info_schema) -> None:
    """
    Import licenses from the schema to the administrative info model.
    
    This function creates BundleLicense objects for each license in the schema
    and associates them with the administrative info model. It also maps the
    access type from the schema to the model.
    
    Args:
        admin_info: The BundleAdministrativeInfo instance to add licenses to.
        admin_info_schema: The administrative info section of the BLAM bundle repository schema.
    """
    # Map access type from schema to model (v1.1 uses public/academic/restricted)
    access = "public"  # Default value
    if admin_info_schema.access and admin_info_schema.access.value:
        access_mapping = {
            SimpletypeAccess51.PUBLIC: "public",
            SimpletypeAccess51.ACADEMIC: "academic",
            SimpletypeAccess51.RESTRICTED: "restricted"
        }
        access = access_mapping.get(admin_info_schema.access.value, "public")
    
    for license_schema in admin_info_schema.license:
        # Handle None or empty values
        license_name = license_schema.license_name or ""
        license_identifier = license_schema.license_identifier or ""
        
        license_model = BundleLicense.objects.create(
            license_name=license_name,
            license_identifier=license_identifier,
            access=access,
        )
        admin_info.licenses.add(license_model)


def import_rights_holders(admin_info: BundleAdministrativeInfo, admin_info_schema) -> None:
    """
    Import rights holders from the schema to the administrative info model.
    
    This function creates BundleRightsHolder objects for each rights holder in the schema
    and associates them with the administrative info model. It also imports the rights
    holder identifiers for each rights holder.
    
    Args:
        admin_info: The BundleAdministrativeInfo instance to add rights holders to.
        admin_info_schema: The administrative info section of the BLAM bundle repository schema.
    """
    for rights_holder_schema in admin_info_schema.rights_holder:
        rights_holder = BundleRightsHolder.objects.create(
            rights_holder_name=rights_holder_schema.rights_holder_name
        )
        
        # Import rights holder identifiers
        for identifier_schema in rights_holder_schema.rights_holder_identifier:
            identifier_type = getattr(identifier_schema, "identifier_type", None)
            identifier = BundleRightsHolderIdentifier.objects.create(
                identifier=identifier_schema.value,
                identifier_type=(getattr(identifier_type, "value", None) or "OTHER").upper(),
            )
            rights_holder.rights_holder_identifiers.add(identifier)
        
        admin_info.rights_holders.add(rights_holder)
