from django.db import transaction
from typing import Any, Optional
from datetime import datetime
from django.utils import timezone
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from lacos.blam.models.collection.collection_header import CollectionHeader


@transaction.atomic
def import_collection_header(cmd_data: Cmd) -> CollectionHeader:
    """
    Import collection header information from BLAM schema to Django models.
    
    Args:
        cmd_data: The parsed BLAM collection repository schema data
        
    Returns:
        The created CollectionHeader instance
    """
    header_data = cmd_data.header
    
    # Create the collection header record
    header = create_collection_header(header_data)
    
    return header


def create_collection_header(header_data: Any) -> CollectionHeader:
    """
    Create a CollectionHeader instance from schema data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The created CollectionHeader instance
    """
    # Extract creator (use first one if multiple are present)
    creator = extract_creator(header_data)
    
    # Extract creation date
    creation_date = extract_creation_date(header_data)
    
    # Extract self link
    self_link = extract_self_link(header_data)
    
    # Extract profile
    profile = extract_profile(header_data)
    
    # Extract collection display name
    collection_display_name = extract_collection_display_name(header_data)
    
    # Create or update the header
    header, created = CollectionHeader.objects.get_or_create(
        md_self_link=self_link,
        defaults={
            'md_creator': creator,
            'md_creation_date': creation_date,
            'md_profile': profile,
            'md_collection_display_name': collection_display_name
        }
    )
    
    return header


def extract_creator(header_data: Any) -> str:
    """
    Extract the creator from the header data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The creator as a string
    """
    # Get the first creator (required in schema)
    if header_data.md_creator and len(header_data.md_creator) > 0:
        return header_data.md_creator[0].value
    return ""


def extract_creation_date(header_data: Any) -> datetime.date:
    """
    Extract the creation date from the header data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The creation date
    """
    if hasattr(header_data, 'md_creation_date') and header_data.md_creation_date:
        return header_data.md_creation_date.value
    return timezone.now().date()


def extract_self_link(header_data: Any) -> str:
    """
    Extract the self link from the header data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The self link as a string
    """
    if hasattr(header_data, 'md_self_link') and header_data.md_self_link:
        return header_data.md_self_link.value
    return ""


def extract_profile(header_data: Any) -> str:
    """
    Extract the profile from the header data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The profile as a string
    """
    if hasattr(header_data, 'md_profile') and header_data.md_profile:
        return header_data.md_profile.value
    return ""


def extract_collection_display_name(header_data: Any) -> Optional[str]:
    """
    Extract the collection display name from the header data.
    
    Args:
        header_data: The header data from the schema
        
    Returns:
        The collection display name as a string or None
    """
    if hasattr(header_data, 'md_collection_display_name') and header_data.md_collection_display_name:
        return header_data.md_collection_display_name.value
    return None
