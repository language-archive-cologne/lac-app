from typing import Dict, Any, List, Optional
from django.db.models import QuerySet
from lacos.blam.models.base_indentifiers import FunderIdentifierTypeChoices
from blam_schemas.bundle.blam_bundle_repository_v1_0 import (
    Cmd,
    FunderIdentifierIdentifierType
)
from lacos.blam.models.base_project_info import (
    ProjectInfo,
    FunderInfo,
    FunderIdentifier
)


def export_project_info(projects: List[ProjectInfo], cmd_data: Cmd) -> None:
    """
    Export project information from Django models to BLAM schema.
    
    Args:
        projects: List of ProjectInfo instances to export
        cmd_data: The BLAM bundle repository schema data to populate
    """
    # Skip if no projects to export
    if not projects:
        return
    
    # Create the project info structure
    project_info = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo()
    
    # Export each project
    for project in projects:
        project_info.project.append(export_project(project))
    
    # Assign to cmd_data
    cmd_data.components.blam_bundle_repository_v1_0.project_info = project_info


def export_project(project: ProjectInfo) -> Any:
    """
    Export a single project to schema format.
    
    Args:
        project: The ProjectInfo instance to export
        
    Returns:
        A project object for the schema
    """
    project_data = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project()
    
    # Set basic fields
    project_data.project_display_name = project.project_display_name
    project_data.project_description = project.project_description
    
    # Export funder information if present
    if project.funder_infos.exists():
        project_data.funder_infos = export_funder_infos(project.funder_infos.all())
    
    return project_data


def export_funder_infos(funders: QuerySet) -> Any:
    """
    Export funder information to schema format.
    
    Args:
        funders: QuerySet of FunderInfo instances
        
    Returns:
        A funder infos container for the schema
    """
    funder_infos = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos()
    
    for funder in funders:
        funder_infos.funder_info.append(export_funder_info(funder))
    
    return funder_infos


def export_funder_info(funder: FunderInfo) -> Any:
    """
    Export a single funder to schema format.
    
    Args:
        funder: The FunderInfo instance
        
    Returns:
        A funder info object for the schema
    """
    funder_data = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo()
    
    # Set required fields
    funder_data.funder_name = funder.funder_name
    
    # Set optional fields
    if funder.grant_identifier:
        funder_data.grant_identifier = funder.grant_identifier
    
    if funder.grant_uri:
        funder_data.grant_uri = funder.grant_uri
    
    if funder.funder_identifiers.exists():
        for identifier in funder.funder_identifiers.all():
            funder_data.funder_identifier.append(export_funder_identifier(identifier))
    
    return funder_data


def export_funder_identifier(identifier: FunderIdentifier) -> Any:
    """
    Export a funder identifier to schema format.
    
    Args:
        identifier: The FunderIdentifier instance
        
    Returns:
        A funder identifier object for the schema
    """
    identifier_data = Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo.FunderIdentifier()
    
    # Set value
    identifier_data.value = identifier.value
    
    # Set identifier type
    identifier_data.identifier_type = map_to_schema_identifier_type(identifier.identifier_type)
    
    return identifier_data


def map_to_schema_identifier_type(id_type: str) -> FunderIdentifierIdentifierType:
    """
    Map model identifier type to schema enum.
    
    Args:
        id_type: The identifier type from the model
        
    Returns:
        The corresponding schema identifier type enum value
    """
    mapping = {
        FunderIdentifierTypeChoices.CROSSREF_FUNDER.value: FunderIdentifierIdentifierType.CROSSREF_FUNDER,
        FunderIdentifierTypeChoices.ISNI.value: FunderIdentifierIdentifierType.ISNI,
        FunderIdentifierTypeChoices.GRID.value: FunderIdentifierIdentifierType.GRID,
        FunderIdentifierTypeChoices.OTHER.value: FunderIdentifierIdentifierType.OTHER,
    }
    return mapping.get(id_type, FunderIdentifierIdentifierType.CROSSREF_FUNDER)
