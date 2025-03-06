from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.base_project_info import ProjectInfo
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from xsdata.formats.dataclass.parsers import XmlParser

# Import the standalone import functions
from lacos.blam.mappers.collection.read.import_collection_general_info import import_general_info
from lacos.blam.mappers.collection.read.import_collection_publication_info import import_publication_info
from lacos.blam.mappers.collection.read.import_collection_administrative_info import import_administrative_info
from lacos.blam.mappers.collection.read.import_collection_project_info import import_project_info


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
        Imports XML content into Django models
        
        Args:
            xml_content: The XML content to import
            
        Returns:
            The created Collection instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd) -> Collection:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            
        Returns:
            The created Collection instance
        """
        # Import all components
        general_info = cls._import_general_info(cmd_data)
        publication_info = cls._import_publication_info(cmd_data)
        administrative_info = cls._import_administrative_info(cmd_data)
        
        # Get metadata license
        md_license, md_license_uri = cls._extract_metadata_license(cmd_data)
        
        # Create or update collection
        collection = cls._create_or_update_collection(
            general_info, 
            publication_info, 
            administrative_info, 
            md_license, 
            md_license_uri
        )
        
        # Import and link projects
        cls._import_and_link_projects(cmd_data, collection)
        
        return collection
    
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
    def _extract_metadata_license(cls, cmd_data: Cmd) -> tuple:
        """Extract metadata license information from CMD data"""
        repo = cmd_data.components.blam_collection_repository_v1_0
        md_license = repo.mdlicense.value if repo.mdlicense else None
        md_license_uri = repo.mdlicense.uri if repo.mdlicense else None
        return md_license, md_license_uri
    
    @classmethod
    def _create_or_update_collection(
        cls, 
        general_info, 
        publication_info, 
        administrative_info, 
        md_license, 
        md_license_uri
    ) -> Collection:
        """Create or update a Collection with the imported components"""
        collection, created = Collection.objects.get_or_create(
            general_info=general_info,
            defaults={
                'publication_info': publication_info,
                'administrative_info': administrative_info,
                'md_license': md_license,
                'md_license_uri': md_license_uri
            }
        )
        
        # Update fields if the collection already existed
        if not created:
            collection.publication_info = publication_info
            collection.administrative_info = administrative_info
            collection.md_license = md_license
            collection.md_license_uri = md_license_uri
            collection.save()
            
        return collection
    
    @classmethod
    def _import_and_link_projects(cls, cmd_data: Cmd, collection: Collection) -> None:
        """Import project info and link to collection"""
        repo = cmd_data.components.blam_collection_repository_v1_0
        if hasattr(repo, 'project_info') and repo.project_info:
            projects = import_project_info(cmd_data)
            for project in projects:
                collection.projects.add(project) 