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
        # Import mandatory components
        header = import_collection_header(cmd_data)
        # We don't need to import licenses separately as they're handled in import_administrative_info
        general_info = import_general_info(cmd_data)
        publication_info = import_publication_info(cmd_data)
        administrative_info = import_administrative_info(cmd_data)
        structural_info = import_structural_info(cmd_data)
        
        # Import optional project info if available
        project_info = None
        if hasattr(cmd_data.components.blam_collection_repository_v1_0, 'project_info') and cmd_data.components.blam_collection_repository_v1_0.project_info:
            project_info = import_project_info(cmd_data)
            logger.info("Project info found and imported")
        else:
            logger.info("No project info found in XML - this is optional")
        
        # Create or update collection with all components
        collection = cls._create_or_update_collection(
            header,
            general_info, 
            publication_info, 
            project_info,
            administrative_info,
            structural_info
        )
        
        return collection
    
    @classmethod
    def _import_header(cls, cmd_data: Cmd):
        """Import header from CMD data"""
        return import_collection_header(cmd_data)
    
    @classmethod
    def _import_license(cls, cmd_data: Cmd):
        """Import license from CMD data"""
        return import_collection_license(cmd_data)
    
    @classmethod
    def _import_general_info(cls, cmd_data: Cmd):
        """Import general info from CMD data"""
        return import_general_info(cmd_data)
    
    @classmethod
    def _import_publication_info(cls, cmd_data: Cmd):
        """Import publication info from CMD data"""
        return import_publication_info(cmd_data)
    
    @classmethod
    def _import_project_info(cls, cmd_data: Cmd):
        """Import project info from CMD data"""
        return import_project_info(cmd_data)

    @classmethod
    def _import_administrative_info(cls, cmd_data: Cmd):
        """Import administrative info from CMD data"""
        return import_administrative_info(cmd_data)
    
    @classmethod
    def _import_structural_info(cls, cmd_data: Cmd):
        """Import structural info from CMD data"""
        return import_structural_info(cmd_data)

    @classmethod
    def _create_or_update_collection(
        cls, 
        header,
        general_info, 
        publication_info, 
        project_info,
        administrative_info,
        structural_info
    ) -> Collection:
        """Create or update a Collection with the imported components"""
        # Create base collection data with mandatory fields only
        collection_data = {
            'base_header': header,
            'general_info': general_info,
            'publication_info': publication_info,
            'administrative_info': administrative_info,
            'structural_info': structural_info
        }
        
        # Add project_info only if it exists and is not None
        if project_info is not None:
            collection_data['project_info'] = project_info[0] if isinstance(project_info, list) else project_info
            
        # Create or update collection
        collection, created = Collection.objects.get_or_create(
            base_header=header,
            defaults=collection_data
        )
        
        # Update fields if the collection already existed
        if not created:
            for field, value in collection_data.items():
                setattr(collection, field, value)
            collection.save()
            
        return collection
    
# The following methods (resolve_bundle_references, resolve_all_bundle_references) are being removed
# as they seem disconnected from the actual import logic and model relationships.
# Bundle linking is handled during bundle import via the ForeignKey from BundleStructuralInfo.
    