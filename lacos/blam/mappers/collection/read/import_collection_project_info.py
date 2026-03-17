from typing import Any
from django.db import transaction
from lacos.blam.mappers.import_cleanup import delete_unreferenced_records
from lacos.blam.models.base_project_info import (
    ProjectInfo,
    FunderInfo,
    FunderIdentifier
)
from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_2 import (
    FunderIdentifierIdentifierType
)


@transaction.atomic
def import_project_info(cmd_data: Any, collection: Collection) -> list[ProjectInfo]:
    """
    Import project info from a BLAM collection repository schema to Django models.
    
    This function extracts project metadata from the BLAM collection repository schema
    and converts it to Django model representations, including related models for
    funders and funder identifiers.
    
    The entire import process is wrapped in a database transaction to ensure atomicity.
    If any part of the import fails, all database changes will be rolled back.
    
    Args:
        cmd_data: The parsed BLAM collection data containing project info.
        collection: The Collection instance to attach these project infos to.
        
    Returns:
        A list of ProjectInfo instances with all related objects.
    """
    # Get repository component
    repo = cmd_data.components.blam_collection_repository_v1_2
    
    # Check if project_info exists in the schema
    if not hasattr(repo, 'project_info'):
        clear_collection_project_info(collection)
        return []  # Return empty list if no project info in schema
        
    # Extract the project info section from the schema
    project_info_schema = repo.project_info
    
    # Check if project attribute exists and has content
    if not hasattr(project_info_schema, 'project') or not project_info_schema.project:
        clear_collection_project_info(collection)
        return []  # Return empty list if no projects defined
    
    # List to store all project info instances
    project_infos = []
    
    clear_collection_project_info(collection)

    # Process each project in the schema
    for project_schema in project_info_schema.project:
        # Create and populate the project info model
        project_info = create_project_info(project_schema)
        
        # Import funder infos if they exist
        if hasattr(project_schema, 'funder_infos') and project_schema.funder_infos:
            import_funder_infos(project_info, project_schema.funder_infos)
        
        project_infos.append(project_info)
    
    for project_info in project_infos:
        collection.project_infos.add(project_info)
    
    return project_infos


def clear_collection_project_info(collection: Collection) -> None:
    project_ids = list(collection.project_infos.values_list("id", flat=True))
    funder_ids = list(
        FunderInfo.objects.filter(projects__id__in=project_ids).values_list("id", flat=True).distinct()
    )
    identifier_ids = list(
        FunderIdentifier.objects.filter(funder_infos__id__in=funder_ids).values_list("id", flat=True).distinct()
    )

    collection.project_infos.clear()

    delete_unreferenced_records(ProjectInfo, project_ids, ["collections", "bundles"])
    delete_unreferenced_records(FunderInfo, funder_ids, ["projects"])
    delete_unreferenced_records(FunderIdentifier, identifier_ids, ["funder_infos"])


def create_project_info(project_schema) -> ProjectInfo:
    """
    Create and populate a project info model from schema data.
    
    Args:
        project_schema: The project section of the BLAM collection repository schema.
        
    Returns:
        A ProjectInfo instance with fields populated from the schema.
    """
    # Prepare project data
    project_data = {
        'project_display_name': project_schema.project_display_name,
        'project_description': project_schema.project_description
    }
    
    return ProjectInfo.objects.create(**project_data)


def import_funder_infos(project_info: ProjectInfo, funder_infos_schema) -> None:
    """
    Import funder information from the schema to the project info model.
    
    This function creates FunderInfo objects for each funder in the schema
    and associates them with the project info model. It also imports funder
    identifiers for each funder.
    
    Args:
        project_info: The ProjectInfo instance to add funders to.
        funder_infos_schema: The funder infos section of the project schema.
    """
    for funder_info_schema in funder_infos_schema.funder_info:
        # Prepare funder data
        funder_data = {
            'funder_name': funder_info_schema.funder_name
        }
        
        # Set optional fields if they exist
        if hasattr(funder_info_schema, 'grant_identifier') and funder_info_schema.grant_identifier:
            funder_data['grant_identifier'] = funder_info_schema.grant_identifier
        
        if hasattr(funder_info_schema, 'grant_uri') and funder_info_schema.grant_uri:
            funder_data['grant_uri'] = funder_info_schema.grant_uri
        
        funder_info = FunderInfo.objects.create(**funder_data)
        
        if hasattr(funder_info_schema, 'funder_identifier') and funder_info_schema.funder_identifier:
            # Handle both single object and list cases
            identifiers = funder_info_schema.funder_identifier
            if not isinstance(identifiers, (list, tuple)):
                identifiers = [identifiers]
            for identifier_schema in identifiers:
                id_type_mapping = {
                    FunderIdentifierIdentifierType.CROSSREF_FUNDER: "crossref_funder",
                    FunderIdentifierIdentifierType.ISNI: "isni",
                    FunderIdentifierIdentifierType.GRID: "grid",
                    FunderIdentifierIdentifierType.OTHER: "other"
                }
                id_type = id_type_mapping.get(identifier_schema.identifier_type, "crossref_funder")

                identifier = FunderIdentifier.objects.create(
                    value=identifier_schema.value,
                    identifier_type=id_type
                )

                funder_info.funder_identifiers.add(identifier)
        
        # Add the funder to the project
        project_info.funder_infos.add(funder_info)
