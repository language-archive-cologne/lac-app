from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.base_project_info import ProjectInfo
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd

# Import the standalone import functions
from lacos.blam.mappers.bundle.read.import_general_info import import_general_info
from lacos.blam.mappers.bundle.read.import_publication_info import import_publication_info
from lacos.blam.mappers.bundle.read.import_structural_info import import_structural_info
from lacos.blam.mappers.bundle.read.import_administrative_info import import_administrative_info
from lacos.blam.mappers.bundle.read.import_project_info import import_project_info


class BundleImporter:
    """
    Handles importing BLAM XML into Django models.
    """
    
    @staticmethod
    def validate_xml(xml_content: str) -> Cmd:
        """
        Validates XML against schema and parses into dataclass
        Returns parsed Cmd object if valid, raises ValidationError if invalid
        """
        try:
            # Using the generated dataclasses to parse XML
            cmd_data = Cmd.from_xml(xml_content)
            return cmd_data
        except Exception as e:
            raise ValidationError(f"Invalid BLAM bundle XML: {str(e)}")
    
    @classmethod
    @transaction.atomic
    def import_from_xml(cls, xml_content: str, collection_id: Optional[int] = None) -> Bundle:
        """
        Imports XML content into Django models
        
        Args:
            xml_content: The XML content to import
            collection_id: Optional ID of the collection this bundle belongs to
            
        Returns:
            The created Bundle instance
        """
        cmd_data = cls.validate_xml(xml_content)
        return cls._import_cmd_to_models(cmd_data, collection_id)
    
    @classmethod
    def _import_cmd_to_models(cls, cmd_data: Cmd, collection_id: Optional[int] = None) -> Bundle:
        """
        Converts Cmd object to Django models
        
        Args:
            cmd_data: The validated CMD data object
            collection_id: Optional ID of the collection this bundle belongs to
            
        Returns:
            The created Bundle instance
        """
        # Import all components
        general_info = cls._import_general_info(cmd_data)
        publication_info = cls._import_publication_info(cmd_data)
        administrative_info = cls._import_administrative_info(cmd_data)
        structural_info = cls._import_structural_info(cmd_data, collection_id)
        
        # Get metadata license
        md_license, md_license_uri = cls._extract_metadata_license(cmd_data)
        
        # Create or update bundle
        bundle = cls._create_or_update_bundle(
            general_info, 
            publication_info, 
            administrative_info, 
            structural_info, 
            md_license, 
            md_license_uri
        )
        
        # Import and link projects
        cls._import_and_link_projects(cmd_data, bundle)
        
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
    def _import_structural_info(cls, cmd_data: Cmd, collection_id: Optional[int]):
        """Import structural info from CMD data if collection_id is provided"""
        if collection_id:
            return import_structural_info(cmd_data, collection_id)
        return None
    
    @classmethod
    def _extract_metadata_license(cls, cmd_data: Cmd) -> tuple:
        """Extract metadata license information from CMD data"""
        repo = cmd_data.components.blam_bundle_repository_v1_0
        md_license = repo.md_license.value if repo.md_license else None
        md_license_uri = repo.md_license.uri if repo.md_license else None
        return md_license, md_license_uri
    
    @classmethod
    def _create_or_update_bundle(
        cls, 
        general_info, 
        publication_info, 
        administrative_info, 
        structural_info, 
        md_license, 
        md_license_uri
    ) -> Bundle:
        """Create or update a Bundle with the imported components"""
        bundle, created = Bundle.objects.get_or_create(
            general_info=general_info,
            defaults={
                'publication_info': publication_info,
                'administrative_info': administrative_info,
                'structural_info': structural_info,
                'md_license': md_license,
                'md_license_uri': md_license_uri
            }
        )
        
        # Update fields if the bundle already existed
        if not created:
            bundle.publication_info = publication_info
            bundle.administrative_info = administrative_info
            bundle.structural_info = structural_info
            bundle.md_license = md_license
            bundle.md_license_uri = md_license_uri
            bundle.save()
            
        return bundle
    
    @classmethod
    def _import_and_link_projects(cls, cmd_data: Cmd, bundle: Bundle) -> None:
        """Import project info and link to bundle"""
        repo = cmd_data.components.blam_bundle_repository_v1_0
        if hasattr(repo, 'project_info') and repo.project_info:
            projects = import_project_info(cmd_data)
            for project in projects:
                bundle.projects.add(project)