from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError
import logging
import uuid

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd
from xsdata.formats.dataclass.parsers import XmlParser

# Import the standalone import functions
from lacos.blam.mappers.bundle.read.import_bundle_general_info import import_general_info
from lacos.blam.mappers.bundle.read.import_bundle_publication_info import import_publication_info
from lacos.blam.mappers.bundle.read.import_bundle_structural_info import import_structural_info
from lacos.blam.mappers.bundle.read.import_bundle_administrative_info import import_administrative_info
from lacos.blam.mappers.bundle.read.import_bundle_project_info import import_project_info
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
        try:
            # Using xsdata parser to parse XML into Cmd dataclass
            parser = XmlParser()
            cmd_data = parser.from_string(xml_content, Cmd)
            return cmd_data
        except Exception as e:
            raise ValidationError(f"Invalid BLAM bundle XML: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str) -> Bundle:
        """
        Imports XML content into Django models
        
        Args:
            xml_content: The XML content to import
            
        Returns:
            The created or existing Bundle instance
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
                logger.info(f"Found existing bundle with identifier {md_self_link}, returning without changes")
                return existing_bundle
        
        # No existing bundle found, create a new one
        bundle = cls._import_cmd_to_models(cmd_data)
        
        # Set the identifier on the bundle
        if md_self_link:
            bundle.identifier = md_self_link
            bundle.save(update_fields=['identifier'])
        
        return bundle
    
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
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Bundle:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            
        Returns:
            The created or updated Bundle instance
        """
        # First, create a new Bundle
        bundle = cls._create_bundle(cmd_data)
        
        try:
            # Import header first, as it's required
            header = import_bundle_header(cmd_data, bundle)
            if not header:
                # Decide how to handle missing header: raise error or return None/empty?
                logger.error("Bundle import failed: Could not import BundleHeader.")
                raise ValidationError("Bundle import failed due to missing or invalid header information.")
                # Or return None, depending on desired behavior

            # Import other components, passing the bundle instance
            cls._import_general_info(cmd_data, bundle)
            cls._import_publication_info(cmd_data, bundle)
            cls._import_administrative_info(cmd_data, bundle)
            cls._import_structural_info(cmd_data, bundle)
            
            # No need to call _create_or_update_bundle since the bundle was already created
            # and all relations have been established
            
            logger.info(f"Bundle import completed for '{header.md_self_link}'.")
            return bundle
            
        except Exception as e:
            # If any error occurs, the transaction will be rolled back automatically
            # No need to manually delete the bundle
            logger.error(f"Error during bundle import: {e}", exc_info=True)
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
        """Import structural info from CMD data"""
        try:
            # Navigate through parsed XML data
            repo_info = cmd_data.components.blam_bundle_repository_v1_0
            struct_info_data = repo_info.bundle_structural_info
            collection_ref = struct_info_data.bundle_is_member_of_collection

            if not collection_ref:
                 logger.warning("Bundle XML is missing BundleIsMemberOfCollection reference. Cannot link to collection.")
                 return None # Cannot proceed without collection reference
                 
            collection_identifier_value = collection_ref.value
            # Get the identifier type enum from parsed data
            collection_identifier_type_enum = collection_ref.identifier_type

            # --- Map Enum to Model String Choice ---
            from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
            collection_identifier_type_str = None
            if collection_identifier_type_enum: # Check if type was provided
                 # Assumes enum .name ('HANDLE') matches uppercased choice display name ('Handle')
                 for choice_value, choice_name in IdentifierTypeChoices.choices:
                      if collection_identifier_type_enum.name == choice_name.upper():
                           collection_identifier_type_str = choice_value
                           break
            else:
                 # Handle case where IdentifierType attribute is missing in XML
                 # Defaulting might be an option, or raising an error/warning
                 logger.warning("BundleIsMemberOfCollection IdentifierType attribute missing in XML. Cannot determine collection identifier type.")
                 return None # Or default if appropriate

            if not collection_identifier_type_str:
                # Log if mapping failed (and enum wasn't None)
                logger.error(f"Could not map bundle's collection identifier type enum '{collection_identifier_type_enum}' to a string choice.")
                return None
            # ---------------------------------------

            # Call the standalone importer function
            # It receives the full cmd_data and extracts what it needs internally
            return import_structural_info(
                cmd_data,
                collection_identifier_value,
                collection_identifier_type_str,
                bundle
            )
        except AttributeError as e:
            logger.error(f"Could not extract collection reference from bundle CMD data: {e}", exc_info=True)
            return None
        except ValueError as e:
            # Log the error (e.g., collection not found) but don't fail the entire import
            logger.warning(f"Failed to import structural info (likely collection not found): {str(e)}")
            return None
        except Exception as e:
            # Catch any other unexpected errors during extraction or import
            logger.error(f"Unexpected error during structural info import: {e}", exc_info=True)
            return None