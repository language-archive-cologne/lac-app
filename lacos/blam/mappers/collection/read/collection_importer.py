from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from xsdata.formats.dataclass.parsers import XmlParser

# Import the standalone import functions
from lacos.blam.mappers.collection.read.import_collection_header import import_collection_header
from lacos.blam.mappers.collection.read.import_collection_license import import_collection_license
from lacos.blam.mappers.collection.read.import_collection_general_info import import_general_info
from lacos.blam.mappers.collection.read.import_collection_publication_info import import_publication_info
from lacos.blam.mappers.collection.read.import_collection_administrative_info import import_administrative_info
from lacos.blam.mappers.collection.read.import_collection_project_info import import_project_info
from lacos.blam.mappers.collection.read.import_collection_structural_info import import_structural_info

logger = logging.getLogger(__name__)

class CollectionImporter:
    """
    Handles importing BLAM Collection XML into Django models.
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
            raise ValidationError(f"Invalid BLAM collection XML: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str) -> Collection:
        """
        Import a collection from XML content.
        
        This method validates the XML content, imports it into Django models,
        and returns the created Collection instance.
        
        Args:
            xml_content: The XML content to import.
            
        Returns:
            The imported Collection instance.
        """
        # Validate the XML content
        cmd_data = cls.validate_xml(xml_content)
        
        # Import the CMD data to Django models
        collection = cls._import_cmd_to_models(cmd_data)
        
        return collection
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Collection:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            
        Returns:
            The created Collection instance
        """
        # First, create the Collection object (a lightweight object without components)
        collection = cls._create_collection(cmd_data)
        
        try:
            # Then import all components, passing the collection to each import function
            cls._import_header(cmd_data, collection)
            cls._import_general_info(cmd_data, collection)
            cls._import_publication_info(cmd_data, collection)
            cls._import_administrative_info(cmd_data, collection)
            cls._import_structural_info(cmd_data, collection)
            cls._import_license(cmd_data, collection)
            
            # Import optional project info if available
            if hasattr(cmd_data.components.blam_collection_repository_v1_0, 'project_info') and cmd_data.components.blam_collection_repository_v1_0.project_info:
                cls._import_project_info(cmd_data, collection)
                logger.info("Project info found and imported")
            else:
                logger.info("No project info found in XML - this is optional")
            
            return collection
            
        except Exception as e:
            # If any error occurs, the transaction will be rolled back automatically
            # No need to manually delete the collection
            logger.error(f"Error during collection import: {e}", exc_info=True)
            raise e
    
    @classmethod
    def _create_collection(cls, cmd_data: Cmd) -> Collection:
        """
        Create a new Collection for the import process
        
        Args:
            cmd_data: The validated CMD data
            
        Returns:
            A new Collection instance
        """
        # Simply create a new Collection for this import
        collection = Collection.objects.create()
        logger.info(f"Created new Collection with ID {collection.id}")
        return collection
    
    @classmethod
    def _import_header(cls, cmd_data: Cmd, collection: Collection):
        """
        Import header from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        header = import_collection_header(cmd_data, collection)
        logger.info(f"Imported header for collection {collection.id}")
        return header
    
    @classmethod
    def _import_license(cls, cmd_data: Cmd, collection: Collection):
        """
        Import license from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        license_obj = import_collection_license(cmd_data, collection)
        if license_obj:
            logger.info(f"Imported license {license_obj.license_name} for collection {collection.id}")
        else:
            logger.info(f"No license found for collection {collection.id}")
        return license_obj
    
    @classmethod
    def _import_general_info(cls, cmd_data: Cmd, collection: Collection):
        """
        Import general info from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        general_info = import_general_info(cmd_data, collection)
        logger.info(f"Imported general info for collection {collection.id}")
        return general_info
    
    @classmethod
    def _import_publication_info(cls, cmd_data: Cmd, collection: Collection):
        """
        Import publication info from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        publication_info = import_publication_info(cmd_data, collection)
        logger.info(f"Imported publication info for collection {collection.id}")
        return publication_info
    
    @classmethod
    def _import_project_info(cls, cmd_data: Cmd, collection: Collection):
        """
        Import project info from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        project_info = import_project_info(cmd_data, collection)
        logger.info(f"Imported project info for collection {collection.id}")
        return project_info

    @classmethod
    def _import_administrative_info(cls, cmd_data: Cmd, collection: Collection):
        """
        Import administrative info from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        administrative_info = import_administrative_info(cmd_data, collection)
        logger.info(f"Imported administrative info for collection {collection.id}")
        return administrative_info
    
    @classmethod
    def _import_structural_info(cls, cmd_data: Cmd, collection: Collection):
        """
        Import structural info from CMD data and attach to collection
        
        Args:
            cmd_data: The validated CMD data
            collection: The Collection instance to attach to
        """
        # Pass the collection to the import function
        structural_info = import_structural_info(cmd_data, collection)
        logger.info(f"Imported structural info for collection {collection.id}")
        return structural_info
    
# The following methods (resolve_bundle_references, resolve_all_bundle_references) are being removed
# as they seem disconnected from the actual import logic and model relationships.
# Bundle linking is handled during bundle import via the ForeignKey from BundleStructuralInfo.
    