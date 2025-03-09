from django.db import transaction
from typing import Any, Optional, Tuple
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd


@transaction.atomic
def import_collection_license(cmd_data: Cmd) -> Tuple[str, Optional[str]]:
    """
    Import collection license information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM collection repository schema data
        
    Returns:
        A tuple containing the license value and license URI
    """
    # Get the repository component
    repo = cmd_data.components.blam_collection_repository_v1_0
    
    # Extract license information
    license_value, license_uri = extract_license_info(repo)
    
    return license_value, license_uri


def extract_license_info(repo: Any) -> Tuple[str, Optional[str]]:
    """
    Extract license information from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        A tuple containing the license value and license URI
    """
    # Extract license value
    license_value = extract_license_value(repo)
    
    # Extract license URI
    license_uri = extract_license_uri(repo)
    
    return license_value, license_uri


def extract_license_value(repo: Any) -> str:
    """
    Extract the license value from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        The license value as a string
    """
    if hasattr(repo, 'mdlicense') and repo.mdlicense:
        return repo.mdlicense.value
    return ""


def extract_license_uri(repo: Any) -> Optional[str]:
    """
    Extract the license URI from the repository component.
    
    Args:
        repo: The repository component from the schema
        
    Returns:
        The license URI as a string or None
    """
    if hasattr(repo, 'mdlicense') and repo.mdlicense and hasattr(repo.mdlicense, 'uri'):
        return repo.mdlicense.uri
    return None 