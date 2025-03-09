from dataclasses import asdict
from typing import Any, Optional, List
from django.db import transaction
from django.core.exceptions import ValidationError

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.base_project_info import ProjectInfo
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
        # Import all components
        header = import_collection_header(cmd_data)
        license = import_collection_license(cmd_data)
        general_info = import_general_info(cmd_data)
        publication_info = import_publication_info(cmd_data)
        project_info = import_project_info(cmd_data)
        administrative_info = import_administrative_info(cmd_data)
        structural_info = import_structural_info(cmd_data)


        # Create or update collection
        collection = cls._create_or_update_collection(
            header,
            license,
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
        license,
        general_info, 
        publication_info, 
        project_info,
        administrative_info, 
        structural_info
    ) -> Collection:
        """Create or update a Collection with the imported components"""
        collection, created = Collection.objects.get_or_create(
            base_header=header,
            base_license=license,
            general_info=general_info,
            publication_info=publication_info,
            project_info=project_info,
            administrative_info=administrative_info,
            structural_info=structural_info
        )
        
        # Update fields if the collection already existed
        if not created:
            collection.base_header = header
            collection.base_license = license
            collection.general_info = general_info
            collection.publication_info = publication_info
            collection.project_info = project_info
            collection.administrative_info = administrative_info
            collection.structural_info = structural_info
            collection.save()
            
        return collection
    
    @classmethod
    def resolve_bundle_references(cls, collection: Collection) -> int:
        """
        Resolve bundle references for a collection.
        
        This method attempts to link collection member references to actual bundles
        if they exist in the system. It uses the two-phase reference approach where
        identifiers are stored first, and then resolved to actual bundles when available.
        
        Args:
            collection: The Collection instance to resolve bundle references for.
            
        Returns:
            The number of successfully resolved bundle references.
        """
        resolved_count = 0
        
        # Get all collection members
        if hasattr(collection, 'members') and collection.members:
            # Get all member references
            member_references = collection.members.member_references.filter(bundle__isnull=True)
            
            # Try to resolve each reference
            for member in member_references:
                if member.resolve_bundle():
                    resolved_count += 1
        
        return resolved_count

    @classmethod
    def resolve_all_bundle_references(cls) -> dict:
        """
        Resolve all unresolved bundle references across all collections.
        
        This method is useful for batch processing after importing multiple bundles,
        to establish links between collections and bundles.
        
        Returns:
            A dictionary with collection IDs as keys and the number of resolved references as values.
        """
        from lacos.blam.models.collection.collection_repository import Collection
        
        results = {}
        
        # Process all collections
        for collection in Collection.objects.all():
            resolved_count = cls.resolve_bundle_references(collection)
            if resolved_count > 0:
                results[str(collection.id)] = resolved_count
        
        return results
    