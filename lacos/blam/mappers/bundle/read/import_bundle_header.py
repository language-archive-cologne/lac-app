import logging
from typing import Any, Optional

from blam_schemas.bundle.blam_bundle_repository_v1_1 import Cmd
from lacos.blam.models.bundle.bundle_header import BundleHeader

logger = logging.getLogger(__name__)

def import_bundle_header(cmd_data: Cmd, bundle: 'Bundle') -> Optional[BundleHeader]:
    """Imports the CMDI header information from Cmd data into a BundleHeader model.

    Args:
        cmd_data: The parsed Cmd data object.
        bundle: The Bundle instance to associate the header with.

    Returns:
        The created or updated BundleHeader instance, or None if header data is missing.
    """
    if not cmd_data or not cmd_data.header:
        logger.warning("CMD data or Header is missing. Cannot import BundleHeader.")
        return None

    header_data = cmd_data.header

    # Extract required fields
    md_self_link = header_data.md_self_link.value if header_data.md_self_link else None
    if not md_self_link:
        logger.error("MdSelfLink is missing in Header. Cannot uniquely identify BundleHeader.")
        # Depending on requirements, you might raise an error or return None
        return None # Cannot proceed without a unique identifier

    md_creator_list = header_data.md_creator
    # Assuming the first creator is the primary one for this field
    md_creator = md_creator_list[0].value if md_creator_list else "Unknown Creator"

    # Get the XmlDate object, or None
    xml_date_obj = header_data.md_creation_date.value if header_data.md_creation_date else None
    # Convert to Python date object if not None
    python_date_obj = xml_date_obj.to_date() if xml_date_obj else None

    md_profile = header_data.md_profile.value if header_data.md_profile else None

    # Extract metadata license from repository mdlicense tag
    md_license, md_license_uri = _extract_md_license_fields(cmd_data)

    # Prepare data for update_or_create
    header_defaults = {
        'md_creator': md_creator,
        'md_creation_date': python_date_obj,
        'md_profile': md_profile,
        'bundle': bundle,
        'md_license': md_license,
        'md_license_uri': md_license_uri,
    }

    # Remove None values to avoid overriding existing fields with None during update
    header_defaults = {k: v for k, v in header_defaults.items() if v is not None}

    try:
        bundle_header, created = BundleHeader.objects.update_or_create(
            md_self_link=md_self_link,
            defaults=header_defaults
        )
        
        status = "created" if created else "updated"
        logger.info(f"BundleHeader with self-link '{md_self_link}' {status} and associated with bundle.")
        return bundle_header
    except Exception as e:
        logger.error(f"Failed to create or update BundleHeader with self-link '{md_self_link}': {e}", exc_info=True)
        return None


def _extract_md_license_fields(cmd_data: Any) -> tuple[Optional[str], Optional[str]]:
    """Extract MDLicense value and URI from the bundle repository component."""
    components = getattr(cmd_data, "components", None)
    if not components:
        return None, None

    repository = getattr(components, "blam_bundle_repository_v1_1", None)
    mdlicense = getattr(repository, "mdlicense", None) if repository else None
    if mdlicense:
        value = getattr(mdlicense, "value", None)
        uri = getattr(mdlicense, "uri", None)
        return (
            str(value).strip() or None if value else None,
            str(uri).strip() or None if uri else None,
        )

    return None, None
