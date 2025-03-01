from typing import Dict, Any, List, Optional
from django.db.models import QuerySet
from datetime import date
from lacos.blam.models.base_indentifiers import AccessTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd,
    RightsHolderIdentifierIdentifierType,
    ComplextypeAccess51 as AccessType
)
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo,
    BundleIdenticalResource,
    BundleLicense,
    BundleRightsHolder,
    BundleRightsHolderIdentifier
)
from xsdata.models.datatype import XmlDate

# Type aliases for nested classes from the schema
BundleAdministrativeInfoType = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo
LicenseType = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.License
RightsHolderType = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder
RightsHolderIdentifierType = Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder.RightsHolderIdentifier


def export_administrative_info(administrative_info: BundleAdministrativeInfo, cmd_data: Cmd) -> None:
    """
    Export bundle administrative information from Django models to BLAM schema.
    
    Args:
        administrative_info: The BundleAdministrativeInfo instance to export
        cmd_data: The BLAM bundle repository schema data to populate
    """
    # Create the bundle administrative info structure
    bundle_info = BundleAdministrativeInfoType()
    
    # Set identical resources if present
    if administrative_info.is_identical_to.exists():
        bundle_info.bundle_is_identical_to = [
            resource.uri for resource in administrative_info.is_identical_to.all()
        ]
    
    # Set derivation if present
    if administrative_info.is_derivation_of:
        bundle_info.bundle_is_derivation_of = administrative_info.is_derivation_of
    
    # Set access
    bundle_info.access = create_access_type(administrative_info)
    
    # Set availability date
    bundle_info.availability_date = create_availability_date(administrative_info.availability_date)
    
    # Set licenses
    bundle_info.license = [
        export_license(license) for license in administrative_info.licenses.all()
    ]
    
    # Set rights holders
    bundle_info.rights_holder = [
        export_rights_holder(rights_holder) for rights_holder in administrative_info.rights_holders.all()
    ]
    
    # Assign to cmd_data
    cmd_data.components.blam_bundle_repository_v1_0.bundle_administrative_info = bundle_info


def create_access_type(administrative_info: BundleAdministrativeInfo) -> AccessType:
    """
    Create an access type object from the model.
    
    Args:
        administrative_info: The BundleAdministrativeInfo instance
        
    Returns:
        An access type object for the schema
    """
    # Get access type from the first license
    # This assumes that all licenses have the same access type
    access = AccessType()
    
    if administrative_info.licenses.exists():
        first_license = administrative_info.licenses.first()
        access.value = map_to_schema_access_type(first_license.access)
    else:
        # Default to OPEN if no licenses are defined
        access.value = "open"
    
    return access


def map_to_schema_access_type(access_type: str) -> str:
    """
    Map model access type to schema access type.
    
    Args:
        access_type: The access type from the model
        
    Returns:
        The corresponding schema access type value
    """
    mapping = {
        AccessTypeChoices.OPEN.value: "open",
        AccessTypeChoices.RESTRICTED.value: "restricted",
        AccessTypeChoices.CLOSED.value: "closed",
    }
    return mapping.get(access_type, "open")


def create_availability_date(availability_date: date) -> XmlDate:
    """
    Create an availability date object for the schema.
    
    Args:
        availability_date: The date from the model
        
    Returns:
        An XmlDate object for the schema
    """
    return XmlDate.from_date(availability_date)


def export_license(license: BundleLicense) -> LicenseType:
    """
    Export a license to schema format.
    
    Args:
        license: The BundleLicense instance
        
    Returns:
        A license object for the schema
    """
    license_data = LicenseType()
    license_data.license_name = license.license_name
    license_data.license_identifier = license.license_identifier
    return license_data


def export_rights_holder(rights_holder: BundleRightsHolder) -> RightsHolderType:
    """
    Export a rights holder to schema format.
    
    Args:
        rights_holder: The BundleRightsHolder instance
        
    Returns:
        A rights holder object for the schema
    """
    rights_holder_data = RightsHolderType()
    rights_holder_data.rights_holder_name = rights_holder.rights_holder_name
    
    # Add identifiers if present
    if rights_holder.rights_holder_identifiers.exists():
        rights_holder_data.rights_holder_identifier = [
            export_rights_holder_identifier(identifier) 
            for identifier in rights_holder.rights_holder_identifiers.all()
        ]
    
    return rights_holder_data


def export_rights_holder_identifier(identifier: BundleRightsHolderIdentifier) -> RightsHolderIdentifierType:
    """
    Export a rights holder identifier to schema format.
    
    Args:
        identifier: The BundleRightsHolderIdentifier instance
        
    Returns:
        A rights holder identifier object for the schema
    """
    identifier_data = RightsHolderIdentifierType()
    identifier_data.value = identifier.value
    
    # Determine identifier type based on the URL
    identifier_data.identifier_type = determine_identifier_type(identifier.value)
    
    return identifier_data


def determine_identifier_type(url: str) -> RightsHolderIdentifierIdentifierType:
    """
    Determine the identifier type based on the URL.
    
    Args:
        url: The identifier URL
        
    Returns:
        The corresponding identifier type enum value
    """
    if "orcid.org" in url.lower():
        return RightsHolderIdentifierIdentifierType.ORCID
    elif "isni.org" in url.lower():
        return RightsHolderIdentifierIdentifierType.ISNI
    elif "@" in url:
        return RightsHolderIdentifierIdentifierType.EMAIL
    else:
        return RightsHolderIdentifierIdentifierType.OTHER
