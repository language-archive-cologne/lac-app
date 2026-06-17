import io
import logging
import unicodedata
import uuid
from typing import Any, Optional, Tuple
import xml.etree.ElementTree as ET

from django.core.exceptions import ValidationError
from django.db import transaction

from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd as CmdV10
from blam_schemas.bundle.blam_bundle_repository_v1_1 import Cmd as CmdV11
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo, BundleResources
from xsdata.formats.dataclass.parsers import XmlParser

# Import the standalone import functions
from lacos.blam.mappers.bundle.read.import_bundle_general_info import import_general_info
from lacos.blam.mappers.bundle.read.import_bundle_publication_info import import_publication_info
from lacos.blam.mappers.bundle.read.import_bundle_structural_info import import_structural_info
from lacos.blam.mappers.bundle.read.import_bundle_administrative_info import import_administrative_info
from lacos.blam.mappers.bundle.read.import_bundle_project_info import import_project_info
from lacos.blam.mappers.bundle.read.import_bundle_header import import_bundle_header

logger = logging.getLogger(__name__)

BLAM_VERSION_1_0 = "1.0"
BLAM_VERSION_1_1 = "1.1"


class BundleImporter:
    """
    Handles importing BLAM Bundle XML into Django models.
    """
    
    @staticmethod
    def validate_xml(xml_content: str) -> Any:
        """
        Validates XML against schema and parses into dataclass
        Returns parsed Cmd object if valid, raises ValidationError if invalid
        """
        # Normalize to Unicode NFC for consistent character representation
        xml_content = unicodedata.normalize("NFC", xml_content)

        version = BundleImporter._detect_version(xml_content)
        if version == BLAM_VERSION_1_1:
            return BundleImporter._parse_v11(xml_content)
        if version == BLAM_VERSION_1_0:
            return BundleImporter._parse_v10(xml_content)
        raise ValidationError(f"Unsupported BLAM bundle version: {version}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(
        cls, xml_content: str, update_existing: bool = False
    ) -> Optional[Tuple[Bundle, Optional[uuid.UUID]]]:
        """
        Imports XML content into Django models
        
        Args:
            xml_content: The XML content to import
            
        Returns:
            Tuple (Bundle instance, BundleResources ID or None) if successful, None otherwise.
        """
        # Validate the XML content
        cmd_data = cls.validate_xml(xml_content)
        
        # Extract the MD self link identifier from the header
        md_self_link = None
        if cmd_data.header and cmd_data.header.md_self_link:
            md_self_link = cmd_data.header.md_self_link.value
            
            # If we have an md_self_link, check if a bundle already exists
            existing_bundle = Bundle.objects.filter(identifier=md_self_link).first()
            if existing_bundle:
                logger.info(
                    "Found existing bundle with identifier %s",
                    md_self_link,
                )
                existing_bundle_resources_id = cls._get_bundle_resources_id(existing_bundle)
                if not update_existing:
                    logger.info("Update mode disabled; returning without changes.")
                    return (existing_bundle, existing_bundle_resources_id)
                return cls._update_existing_bundle(
                    existing_bundle,
                    cmd_data,
                    md_self_link,
                    existing_bundle_resources_id,
                )
        
        # No existing bundle found, create a new one
        bundle, bundle_resources_id = cls._import_cmd_to_models(cmd_data)
        
        # Set the identifier on the bundle if not already set by header import
        if md_self_link and not bundle.identifier == md_self_link:
            bundle.identifier = md_self_link
            bundle.save(update_fields=['identifier'])
        
        return (bundle, bundle_resources_id)

    @classmethod
    def _get_bundle_resources_id(cls, bundle: Bundle) -> Optional[uuid.UUID]:
        """Return the BundleResources ID if one exists for this bundle."""
        try:
            related_resources = bundle.resources.first()
            if related_resources:
                logger.info(
                    "Found existing BundleResources ID %s for bundle %s",
                    related_resources.id,
                    bundle.identifier,
                )
                return related_resources.id
            logger.warning(
                "Existing bundle %s found, but no associated BundleResources object found.",
                bundle.identifier,
            )
        except Exception as exc:
            logger.error(
                "Error fetching BundleResources for existing bundle %s: %s",
                bundle.identifier,
                exc,
            )
        return None

    @classmethod
    def _update_existing_bundle(
        cls,
        bundle: Bundle,
        cmd_data: Any,
        md_self_link: Optional[str],
        existing_bundle_resources_id: Optional[uuid.UUID],
    ) -> Tuple[Bundle, Optional[uuid.UUID]]:
        """Update an existing bundle in place."""
        try:
            header = import_bundle_header(cmd_data, bundle)
            if not header:
                logger.error("Bundle update failed: Could not import BundleHeader.")
                raise ValidationError("Bundle update failed due to missing header information.")

            cls._import_general_info(cmd_data, bundle)
            cls._import_publication_info(cmd_data, bundle)
            cls._import_administrative_info(cmd_data, bundle)
            project_infos = cls._import_project_info(cmd_data, bundle)
            if project_infos:
                logger.info("Project info found and imported for update")
            else:
                logger.info("No project info found in XML - existing links cleared")

            bundle_struct_info = cls._import_structural_info(cmd_data, bundle)
            bundle_resources_id = existing_bundle_resources_id
            if bundle_struct_info and hasattr(bundle_struct_info, "bundle") and bundle_struct_info.bundle:
                bundle_resources_id = cls._get_bundle_resources_id(bundle_struct_info.bundle)

            if md_self_link and bundle.identifier != md_self_link:
                bundle.identifier = md_self_link
                bundle.save(update_fields=["identifier"])

            cls._refresh_file_type_facets(bundle)

            logger.info(
                "Bundle update completed for '%s'.",
                md_self_link or bundle.identifier,
            )
            return (bundle, bundle_resources_id)
        except Exception as exc:
            logger.warning(
                "Bundle update failed for '%s': %s",
                md_self_link or bundle.identifier,
                exc,
            )
            raise
    
    @classmethod
    def _create_bundle(cls, cmd_data: Any) -> Bundle:
        """
        Create a new Bundle for the import process
        
        Args:
            cmd_data: The validated CMD data
            
        Returns:
            A new Bundle instance
        """
        # Create a new bundle with a temporary identifier
        # This will be replaced with the proper md_self_link in import_from_xml
        bundle = Bundle.objects.create(identifier=f"temp-bundle-{uuid.uuid4()}")
        logger.info("Created new Bundle", extra={"bundle_id": bundle.id})
        return bundle

    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Any) -> Tuple[Bundle, Optional[uuid.UUID]]:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            
        Returns:
            Tuple (Created Bundle instance, BundleResources ID or None)
        """
        # First, create a new Bundle
        bundle = cls._create_bundle(cmd_data)
        bundle_resources_id: Optional[uuid.UUID] = None # Initialize
        
        try:
            # Import header first, as it's required
            header = import_bundle_header(cmd_data, bundle)
            if not header:
                logger.error("Bundle import failed: Could not import BundleHeader.")
                raise ValidationError("Bundle import failed due to missing or invalid header information.")

            # Import other components, passing the bundle instance
            cls._import_general_info(cmd_data, bundle)
            cls._import_publication_info(cmd_data, bundle)
            cls._import_administrative_info(cmd_data, bundle)
            project_infos = cls._import_project_info(cmd_data, bundle)
            if project_infos:
                logger.info("Project info found and imported")
            else:
                logger.info("No project info found in XML")
            
            # Import structural info and get BundleResources ID
            bundle_struct_info = cls._import_structural_info(cmd_data, bundle)
            if bundle_struct_info and hasattr(bundle_struct_info, 'bundle') and bundle_struct_info.bundle:
                 # Try to get the BundleResources ID from the related bundle
                try:
                    # Assuming reverse relation 'resources' and it's a ForeignKey
                    br_instance = bundle_struct_info.bundle.resources.first()
                    if br_instance:
                        bundle_resources_id = br_instance.id
                        logger.info("Successfully obtained BundleResources ID during import", extra={"bundle_resources_id": bundle_resources_id})
                    else:
                        logger.warning("Structural info imported, but failed to find associated BundleResources instance.")
                except Exception as e:
                     logger.error("Error getting BundleResources ID after structural info import", extra={"error": e})
            
            cls._refresh_file_type_facets(bundle)

            logger.info("Bundle import completed", extra={"md_self_link": getattr(header, 'md_self_link', 'Unknown')})
            return (bundle, bundle_resources_id)
            
        except Exception as e:
            logger.warning("Bundle import failed: %s", e)
            # Reraise to ensure transaction rollback
            raise e
    
    @classmethod
    def _import_general_info(cls, cmd_data: Any, bundle: Bundle):
        """Import general info from CMD data"""
        return import_general_info(cmd_data, bundle)
    
    @classmethod
    def _import_publication_info(cls, cmd_data: Any, bundle: Bundle):
        """Import publication info from CMD data"""
        return import_publication_info(cmd_data, bundle)
    
    @classmethod
    def _import_administrative_info(cls, cmd_data: Any, bundle: Bundle):
        """Import administrative info from CMD data"""
        return import_administrative_info(cmd_data, bundle)

    @classmethod
    def _import_project_info(cls, cmd_data: Any, bundle: Bundle):
        """Import project info from CMD data"""
        return import_project_info(cmd_data, bundle)

    
    @classmethod
    def _import_structural_info(cls, cmd_data: Any, bundle: Bundle) -> Optional['BundleStructuralInfo']:
        """Import structural info from CMD data. Returns the BundleStructuralInfo object."""
        try:
            # Navigate through parsed XML data
            repo_info = cmd_data.components.blam_bundle_repository_v1_1
            if not repo_info or not repo_info.bundle_structural_info:
                logger.warning("Bundle XML is missing BundleStructuralInfo section.")
                return None
                
            struct_info_data = repo_info.bundle_structural_info
            collection_ref = struct_info_data.bundle_is_member_of_collection

            if not collection_ref:
                 logger.warning("Bundle XML is missing BundleIsMemberOfCollection reference. Cannot link to collection or import structural info.")
                 return None # Cannot proceed without collection reference
                 
            collection_identifier_value = collection_ref.value
            collection_identifier_type_enum = collection_ref.identifier_type

            # --- Map Enum to Model String Choice ---
            from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
            collection_identifier_type_str = None
            if collection_identifier_type_enum:
                 for choice_value, choice_name in IdentifierTypeChoices.choices:
                      if collection_identifier_type_enum.name == choice_name.upper():
                           collection_identifier_type_str = choice_value
                           break
            else:
                 logger.warning("BundleIsMemberOfCollection IdentifierType attribute missing in XML. Cannot determine collection identifier type.")
                 return None 

            if not collection_identifier_type_str:
                logger.error("Could not map bundle's collection identifier type enum to a string choice", extra={"identifier_type_enum": collection_identifier_type_enum})
                return None
            # ---------------------------------------

            # Call the standalone importer function
            # It returns the created/updated BundleStructuralInfo instance or None
            return import_structural_info(
                cmd_data,
                collection_identifier_value,
                collection_identifier_type_str,
                bundle
            )
        except AttributeError as e:
            logger.error("Could not extract data from bundle CMD data for structural info", extra={"error": e}, exc_info=False)
            return None
        except ValueError as e:
            logger.warning("Failed to import structural info (e.g., collection not found)", extra={"error": str(e)})
            return None
        except Exception as e:
            logger.error("Unexpected error during structural info import", extra={"error": e}, exc_info=True)
            return None

    @classmethod
    def _refresh_file_type_facets(cls, bundle: Bundle) -> None:
        from lacos.explorer.services.file_type_facets import (
            refresh_bundle_file_type_facets,
        )

        refresh_bundle_file_type_facets(bundle)

    @staticmethod
    def _detect_version(xml_content: str) -> str:
        try:
            for _, element in ET.iterparse(io.StringIO(xml_content), events=("start",)):
                local = element.tag.split("}")[-1]
                if local.startswith("BLAM-bundle-repository"):
                    if "v1.1" in local or "v1_1" in local:
                        return BLAM_VERSION_1_1
                    return BLAM_VERSION_1_0
                element.clear()
        except ET.ParseError as exc:
            raise ValidationError(f"Invalid BLAM bundle XML: {exc}") from exc
        return BLAM_VERSION_1_0

    @staticmethod
    def _parse_v10(xml_content: str) -> Any:
        parser = XmlParser()
        try:
            cmd = parser.from_string(xml_content, CmdV10)
        except Exception as exc:
            raise ValidationError(f"Invalid BLAM bundle XML: {exc}") from exc

        repository = getattr(cmd.components, "blam_bundle_repository_v1_0", None)
        if repository is not None and not hasattr(cmd.components, "blam_bundle_repository_v1_1"):
            cmd.components.blam_bundle_repository_v1_1 = repository
        return cmd

    @staticmethod
    def _parse_v11(xml_content: str) -> Any:
        parser = XmlParser()
        try:
            cmd = parser.from_string(xml_content, CmdV11)
        except Exception as exc:
            raise ValidationError(f"Invalid BLAM bundle XML: {exc}") from exc

        repository = getattr(cmd.components, "blam_bundle_repository_v1_1", None)
        if repository is not None and not hasattr(cmd.components, "blam_bundle_repository_v1_0"):
            cmd.components.blam_bundle_repository_v1_0 = repository
        return cmd
