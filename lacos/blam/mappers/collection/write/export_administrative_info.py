"""Export collection administrative info to BLAM schema."""

from typing import Optional

from django.db.models import QuerySet
from xsdata.models.datatype import XmlDate

from blam_schemas.collection.blam_collection_repository_v1_2 import (
    Cmd,
    ComplextypeAccess41,
    SimpletypeAccess41,
    RightsHolderIdentifierIdentifierType,
)
from lacos.blam.models.base_administrative_info import AccessTypeChoices
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
    CollectionRightsHolder,
)

# Type aliases
AdminInfoType = Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo
LicenseType = Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.License
RightsHolderType = Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.RightsHolder
RightsHolderIdType = Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.RightsHolder.RightsHolderIdentifier


def export_administrative_info(admin_info: CollectionAdministrativeInfo, repo) -> None:
    """Export collection administrative info to BLAM schema."""
    info = AdminInfoType()

    # Identical resources
    if admin_info.is_identical_to.exists():
        info.collection_is_identical_to = [
            res.uri for res in admin_info.is_identical_to.all()
        ]

    # Derivation
    if admin_info.is_derivation_of:
        info.collection_is_derivation_of = admin_info.is_derivation_of

    # Access level
    info.access = _export_access(admin_info.access_level)

    # Availability date
    info.availability_date = XmlDate.from_date(admin_info.availability_date)

    # Licenses
    info.license = [_export_license(lic) for lic in admin_info.licenses.all()]

    # Rights holders
    info.rights_holder = [
        _export_rights_holder(rh) for rh in admin_info.rights_holders.all()
    ]

    repo.collection_administrative_info = info


def _export_access(access_level: str) -> ComplextypeAccess41:
    access = ComplextypeAccess41()
    # v1.2 uses public/academic/restricted directly
    mapping = {
        "public": SimpletypeAccess41.PUBLIC,
        "academic": SimpletypeAccess41.ACADEMIC,
        "restricted": SimpletypeAccess41.RESTRICTED,
        # Legacy mappings for backward compatibility
        "open": SimpletypeAccess41.PUBLIC,
        "protected": SimpletypeAccess41.ACADEMIC,
        "private": SimpletypeAccess41.RESTRICTED,
        "embargo": SimpletypeAccess41.RESTRICTED,
    }
    access.value = mapping.get(access_level, SimpletypeAccess41.PUBLIC)
    return access


def _export_license(license: CollectionLicense) -> LicenseType:
    lic_data = LicenseType()
    lic_data.license_name = license.license_name
    lic_data.license_identifier = license.license_identifier
    return lic_data


def _export_rights_holder(rights_holder: CollectionRightsHolder) -> RightsHolderType:
    rh_data = RightsHolderType()
    rh_data.rights_holder_name = rights_holder.rights_holder_name

    if rights_holder.rights_holder_identifiers.exists():
        rh_data.rights_holder_identifier = [
            _export_rights_holder_identifier(rhi)
            for rhi in rights_holder.rights_holder_identifiers.all()
        ]

    return rh_data


def _export_rights_holder_identifier(identifier) -> RightsHolderIdType:
    rhi_data = RightsHolderIdType()
    rhi_data.value = identifier.identifier
    rhi_data.identifier_type = _map_rh_id_type(identifier.identifier_type)
    return rhi_data


def _map_rh_id_type(id_type: Optional[str]) -> Optional[RightsHolderIdentifierIdentifierType]:
    if not id_type:
        return None
    mapping = {
        "ORCID": RightsHolderIdentifierIdentifierType.ORCID,
        "ISNI": RightsHolderIdentifierIdentifierType.ISNI,
        "EMAIL": RightsHolderIdentifierIdentifierType.EMAIL,
        "OTHER": RightsHolderIdentifierIdentifierType.OTHER,
    }
    return mapping.get(id_type)
