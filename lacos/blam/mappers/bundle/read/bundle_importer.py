from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

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
            The created Bundle instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Bundle:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            
        Returns:
            The created Bundle instance
        """
        # Import header first, as it's required
        header = import_bundle_header(cmd_data)
        if not header:
            # Decide how to handle missing header: raise error or return None/empty?
            logger.error("Bundle import failed: Could not import BundleHeader.")
            raise ValidationError("Bundle import failed due to missing or invalid header information.")
            # Or return None, depending on desired behavior

        # Import other components
        general_info = cls._import_general_info(cmd_data)
        publication_info = cls._import_publication_info(cmd_data)
        administrative_info = cls._import_administrative_info(cmd_data)
        structural_info = cls._import_structural_info(cmd_data)
        
        # Create or update bundle, passing the header
        bundle = cls._create_or_update_bundle(
            header, # Pass header
            general_info, 
            publication_info, 
            administrative_info, 
            structural_info
        )
        
        return bundle
    
    @classmethod
    def _import_general_info(cls, cmd_data: Cmd):
        """Import general info from CMD data"""
        return import_general_info(cmd_data)
    
    @classmethod
    def _import_publication_info(cls, cmd_data: Cmd):
        """Import publication info from CMD data"""
        return import_publication_info(cmd_data)
    
    @classmethod
    def _import_administrative_info(cls, cmd_data: Cmd):
        """Import administrative info from CMD data"""
        return import_administrative_info(cmd_data)
    
    @classmethod
    def _import_structural_info(cls, cmd_data: Cmd) -> Optional['BundleStructuralInfo']:
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
                collection_identifier_type_str
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
    

    @classmethod
    def _create_or_update_bundle(
        cls, 
        header, # Add header parameter
        general_info, 
        publication_info, 
        administrative_info, 
        structural_info
    ) -> Bundle:
        """Create or update a Bundle with the imported components"""
        # Bundle data now includes the required base_header
        bundle_data = {
            'base_header': header,
            'general_info': general_info,
            'publication_info': publication_info,
            'administrative_info': administrative_info,
        }
        
        # Add structural_info model instance if it was successfully imported
        if structural_info is not None:
            bundle_data['structural_info'] = structural_info
        
        # Create or get bundle using the header's unique self-link as the identifier
        # The defaults dictionary will contain all other fields for creation/update
        bundle, created = Bundle.objects.update_or_create(
            base_header=header, # Use header for lookup
            defaults=bundle_data
        )
        
        # No need for the manual update loop anymore, update_or_create handles it.
        # if not created:
        #     for field, value in bundle_data.items():
        #         # Be careful not to overwrite the lookup key (base_header)
        #         if field != 'base_header': 
        #              setattr(bundle, field, value)
        #     bundle.save()
            
        status = "created" if created else "updated"
        logger.info(f"Bundle linked to header '{header.md_self_link}' {status}.")

        return bundle