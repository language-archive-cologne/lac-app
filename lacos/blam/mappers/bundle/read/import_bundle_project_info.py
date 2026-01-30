from django.db import transaction
from enum import Enum
from typing import Dict, Any, Optional, List

from blam_schemas.bundle.blam_bundle_repository_v1_1 import (
    Cmd, FunderIdentifierIdentifierType
)
from lacos.blam.models.base_project_info import (
    ProjectInfo,
    FunderInfo,
    FunderIdentifier
)
from lacos.blam.models.base_indentifiers import FunderIdentifierTypeChoices



@transaction.atomic
def import_project_info(cmd_data: Cmd, bundle: 'Bundle') -> List[ProjectInfo]:
    """
    Import project information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM bundle repository schema data
        bundle: The Bundle instance to associate the project info with
        
    Returns:
        List of created or updated ProjectInfo instances
    """
    # Check if project info exists in the schema
    if not hasattr(cmd_data.components.blam_bundle_repository_v1_1, 'project_info'):
        return []
    
    project_info_data = cmd_data.components.blam_bundle_repository_v1_1.project_info
    
    # If no projects defined, return empty list
    if not project_info_data or not project_info_data.project:
        return []
    
    # Process each project
    projects = []
    for project_data in project_info_data.project:
        project = create_or_update_project(project_data)
        projects.append(project)
        
        # Associate the project with the bundle
        bundle.projects.add(project)
    
    return projects


def create_or_update_project(project_data: Any) -> ProjectInfo:
    """
    Create or update a ProjectInfo instance from schema data.
    
    Args:
        project_data: The project data from the schema
        
    Returns:
        The created or updated ProjectInfo instance
    """
    # Use project_display_name as the unique identifier
    project, created = ProjectInfo.objects.get_or_create(
        project_display_name=project_data.project_display_name,
        defaults={
            'project_description': project_data.project_description
        }
    )
    
    # If we found an existing record, update the description
    if not created:
        project.project_description = project_data.project_description
        project.save()
    
    # Process funder information if present
    if hasattr(project_data, 'funder_infos') and project_data.funder_infos:
        process_funder_infos(project, project_data.funder_infos.funder_info)
    
    return project


def process_funder_infos(project: ProjectInfo, funder_infos: List[Any]) -> None:
    """
    Process funder information for a project.
    
    Args:
        project: The ProjectInfo instance to associate funders with
        funder_infos: List of funder info data objects from the schema
    """
    # Clear existing funders to avoid duplicates
    # Note: This assumes you want to replace all funders with the new data
    project.funder_infos.clear()
    
    for funder_data in funder_infos:
        funder = create_or_update_funder_info(funder_data)
        project.funder_infos.add(funder)


def create_or_update_funder_info(funder_data: Any) -> FunderInfo:
    """
    Create or update a FunderInfo instance from schema data.
    
    Args:
        funder_data: The funder data from the schema
        
    Returns:
        The created or updated FunderInfo instance
    """
    # Use funder_name as the unique identifier
    funder, created = FunderInfo.objects.get_or_create(
        funder_name=funder_data.funder_name,
        defaults={
            'grant_identifier': getattr(funder_data, 'grant_identifier', None),
            'grant_uri': getattr(funder_data, 'grant_uri', None)
        }
    )
    
    # If we found an existing record, update non-key fields
    if not created:
        funder.grant_identifier = getattr(funder_data, 'grant_identifier', None)
        funder.grant_uri = getattr(funder_data, 'grant_uri', None)
        funder.save()
    
    # Process funder identifiers if present
    if hasattr(funder_data, 'funder_identifier') and funder_data.funder_identifier:
        process_funder_identifiers(funder, funder_data.funder_identifier)
    
    return funder


def process_funder_identifiers(funder: FunderInfo, identifiers: List[Any]) -> None:
    """
    Process funder identifiers for a funder.
    
    Args:
        funder: The FunderInfo instance to associate identifiers with
        identifiers: List of funder identifier data objects from the schema
    """
    funder.funder_identifiers.clear()

    for identifier_data in identifiers:
        identifier = create_funder_identifier(identifier_data)
        funder.funder_identifiers.add(identifier)


def create_funder_identifier(identifier_data: Any) -> FunderIdentifier:
    """
    Create a FunderIdentifier instance from schema data.
    
    Args:
        identifier_data: The identifier data from the schema
        
    Returns:
        The created FunderIdentifier instance
    """
    identifier_type = map_identifier_type(identifier_data.identifier_type)
    
    # Use value and identifier_type as unique identifiers
    identifier, created = FunderIdentifier.objects.get_or_create(
        value=identifier_data.value,
        identifier_type=identifier_type
    )
    
    return identifier


def map_identifier_type(id_type: Optional[FunderIdentifierIdentifierType]) -> str:
    """
    Map schema identifier type to model choices.
    
    Args:
        id_type: The identifier type from the schema
        
    Returns:
        The corresponding identifier type value for the model
    """
    if id_type is None:
        return FunderIdentifierTypeChoices.CROSSREF_FUNDER.value
    
    mapping = {
        FunderIdentifierIdentifierType.CROSSREF_FUNDER: FunderIdentifierTypeChoices.CROSSREF_FUNDER.value,
        FunderIdentifierIdentifierType.ISNI: FunderIdentifierTypeChoices.ISNI.value,
        FunderIdentifierIdentifierType.GRID: FunderIdentifierTypeChoices.GRID.value,
        FunderIdentifierIdentifierType.OTHER: FunderIdentifierTypeChoices.OTHER.value,
    }
    return mapping.get(id_type, FunderIdentifierTypeChoices.CROSSREF_FUNDER.value) 
