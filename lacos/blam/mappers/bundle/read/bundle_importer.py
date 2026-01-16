from dataclasses import asdict
from typing import Any, Optional, List, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError
import logging
import unicodedata
import uuid

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo, BundleResources
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd
from xsdata.formats.dataclass.parsers import XmlParser

# Import the standalone import functions
from lacos.blam.mappers.bundle.read.import_bundle_general_info import import_general_info
from lacos.blam.mappers.bundle.read.import_bundle_publication_info import import_publication_info
from lacos.blam.mappers.bundle.read.import_bundle_structural_info import import_structural_info
from lacos.blam.mappers.bundle.read.import_bundle_administrative_info import import_administrative_info
from lacos.blam.mappers.bundle.read.import_bundle_header import import_bundle_header

logger = logging.getLogger(__name__)
class BundleImporter:
    """
    Handles importing BLAM Bundle XML into Django models.
    """
    
    @staticmethod
    def validate_xml(xml_content: str) -> Cmd:
        """
        Validates XML against schema and parses into dataclass
        Returns parsed Cmd object if valid, raises ValidationError if invalid
        """
        # Normalize to Unicode NFC for consistent character representation
        xml_content = unicodedata.normalize("NFC", xml_content)

        try:
            # Using xsdata parser to parse XML into Cmd dataclass
            parser = XmlParser()
            cmd_data = parser.from_string(xml_content, Cmd)
            return cmd_data
        except Exception as e:
            raise ValidationError(f"Invalid BLAM bundle XML: {str(e)}")
    
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
        cmd_data: Cmd,
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

            bundle_struct_info = cls._import_structural_info(cmd_data, bundle)
            bundle_resources_id = existing_bundle_resources_id
            if bundle_struct_info and hasattr(bundle_struct_info, "bundle") and bundle_struct_info.bundle:
                bundle_resources_id = cls._get_bundle_resources_id(bundle_struct_info.bundle)

            if md_self_link and bundle.identifier != md_self_link:
                bundle.identifier = md_self_link
                bundle.save(update_fields=["identifier"])

            logger.info(
                "Bundle update completed for '%s'.",
                md_self_link or bundle.identifier,
            )
            return (bundle, bundle_resources_id)
        except Exception as exc:
            logger.error("Error during bundle update: %s", exc, exc_info=True)
            raise
    
    @classmethod
    def _create_bundle(cls, cmd_data: Cmd) -> Bundle:
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
        logger.info(f"Created new Bundle with ID {bundle.id}")
        return bundle

    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Tuple[Bundle, Optional[uuid.UUID]]:
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
            
            # Import structural info and get BundleResources ID
            bundle_struct_info = cls._import_structural_info(cmd_data, bundle)
            if bundle_struct_info and hasattr(bundle_struct_info, 'bundle') and bundle_struct_info.bundle:
                 # Try to get the BundleResources ID from the related bundle
                try:
                    # Assuming reverse relation 'resources' and it's a ForeignKey
                    br_instance = bundle_struct_info.bundle.resources.first()
                    if br_instance:
                        bundle_resources_id = br_instance.id
                        logger.info(f"Successfully obtained BundleResources ID: {bundle_resources_id} during import.")
                    else:
                        logger.warning("Structural info imported, but failed to find associated BundleResources instance.")
                except Exception as e:
                     logger.error(f"Error getting BundleResources ID after structural info import: {e}")
            
            logger.info(f"Bundle import completed for '{getattr(header, 'md_self_link', 'Unknown')}'.")
            return (bundle, bundle_resources_id)
            
        except Exception as e:
            logger.error(f"Error during bundle import: {e}", exc_info=True)
            # Reraise to ensure transaction rollback
            raise e
    
    @classmethod
    def _import_general_info(cls, cmd_data: Cmd, bundle: Bundle):
        """Import general info from CMD data"""
        return import_general_info(cmd_data, bundle)
    
    @classmethod
    def _import_publication_info(cls, cmd_data: Cmd, bundle: Bundle):
        """Import publication info from CMD data"""
        return import_publication_info(cmd_data, bundle)
    
    @classmethod
    def _import_administrative_info(cls, cmd_data: Cmd, bundle: Bundle):
        """Import administrative info from CMD data"""
        return import_administrative_info(cmd_data, bundle)

    
    @classmethod
    def _import_structural_info(cls, cmd_data: Cmd, bundle: Bundle) -> Optional['BundleStructuralInfo']:
        """Import structural info from CMD data. Returns the BundleStructuralInfo object."""
        try:
            # Navigate through parsed XML data
            repo_info = cmd_data.components.blam_bundle_repository_v1_0
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
                logger.error(f"Could not map bundle's collection identifier type enum '{collection_identifier_type_enum}' to a string choice.")
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
            logger.error(f"Could not extract data from bundle CMD data for structural info: {e}", exc_info=False) # Less verbose logging
            return None
        except ValueError as e:
            logger.warning(f"Failed to import structural info (e.g., collection not found): {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during structural info import: {e}", exc_info=True)
            return None
