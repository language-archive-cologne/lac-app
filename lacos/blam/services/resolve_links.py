from typing import Optional, List, Tuple
from uuid import UUID
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
import logging

logger = logging.getLogger(__name__)

def get_collection_by_id(collection_id: UUID) -> Optional[Collection]:
    """
    Get a Collection by its ID.
    
    Args:
        collection_id: The UUID of the collection to fetch
        
    Returns:
        Collection object if found, None otherwise
    """
    if collection_id is None:
        logger.warning("get_collection_by_id received None collection_id.")
        return None
        
    try:
        return Collection.objects.get(id=collection_id)
    except Collection.DoesNotExist:
        logger.error(f"Collection {collection_id} not found.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching collection {collection_id}: {e}", exc_info=True)
        return None

def resolve_bundle_links_primary_method(collection: Collection) -> int:
    """
    Attempt to resolve bundle links using the primary CollectionImporter method.
    
    Args:
        collection: The Collection object to resolve links for
        
    Returns:
        Number of resolved links, or 0 if resolution failed
        
    Raises:
        AttributeError: If the collection structure doesn't match expected format
        Exception: For any other unexpected errors
    """
    try:
        return CollectionImporter.resolve_bundle_references(collection)
    except AttributeError:
        # Let this propagate up to trigger the fallback approach
        raise
    except Exception as e:
        logger.error(f"Unexpected error in primary bundle link resolution for collection {collection.id}: {e}", exc_info=True)
        raise

def get_bundle_structural_infos(collection: Collection) -> List[BundleStructuralInfo]:
    """
    Get all BundleStructuralInfo objects linked to a collection.
    
    Args:
        collection: The Collection object to get bundle infos for
        
    Returns:
        List of BundleStructuralInfo objects, or empty list if none found or error occurs
    """
    try:
        return list(collection.bundle_collection.all())
    except Exception as e:
        logger.error(f"Error accessing bundle_collection for collection {collection.id}: {e}", exc_info=True)
        return []

def resolve_links_using_structural_infos(bundle_infos: List[BundleStructuralInfo]) -> Tuple[int, List[str]]:
    """
    Attempt to resolve links using BundleStructuralInfo objects.
    
    Args:
        bundle_infos: List of BundleStructuralInfo objects to resolve
        
    Returns:
        Tuple of (resolved_count, error_messages)
    """
    resolved_count = 0
    errors = []
    
    for member_info in bundle_infos:
        try:
            # First, try using resolve_bundle method on BundleStructuralInfo if it exists
            if hasattr(member_info, 'resolve_bundle'):
                if member_info.resolve_bundle():
                    resolved_count += 1
                    continue
                    
            # If not found or not successful, try the bundle object if available
            if hasattr(member_info, 'bundle') and hasattr(member_info.bundle, 'resolve_bundle'):
                if member_info.bundle.resolve_bundle():
                    resolved_count += 1
                    continue
                    
            # If we get here, no resolution method was found or successful
            errors.append(f"Could not find a 'resolve_bundle' method for BundleStructuralInfo {getattr(member_info, 'id', 'N/A')} or its related Bundle.")
                
        except Exception as e:
            errors.append(f"Error resolving bundle link for BundleStructuralInfo {getattr(member_info, 'id', 'N/A')}: {e}")
    
    for error in errors:
        logger.warning(error)
        
    return resolved_count, errors

def resolve_collection_bundle_links(collection_id: Optional[UUID]) -> Optional[UUID]:
    """
    Resolve CollectionMemberReferences to actual Bundles for a given Collection.
    
    This function attempts to link bundles to their collection using two approaches:
    1. Primary method: Using CollectionImporter.resolve_bundle_references
    2. Fallback method: Directly accessing and processing bundle_collection.all()
    
    Args:
        collection_id: The database ID of the collection to process.
        
    Returns:
        The collection_id to pass down the pipeline, or None if collection not found.
    """
    logger.info(f"Attempting to resolve bundle links for collection ID: {collection_id}")

    if collection_id is None:
        logger.warning("resolve_collection_bundle_links received None collection_id. Skipping.")
        return None
        
    collection = get_collection_by_id(collection_id)
    if not collection:
        return None
        
    # Try the primary method first
    try:
        resolved_count = resolve_bundle_links_primary_method(collection)
        logger.info(f"Resolved {resolved_count} bundle links for collection ID: {collection_id} using primary method")
        return collection_id
    except AttributeError as e:
        # Handle the case where collection.structural_info doesn't have expected structure
        logger.warning(f"Could not resolve bundle links using primary method: {e}. Using fallback approach.")
    except Exception as e:
        # Handle unexpected errors in primary method
        logger.error(f"Error resolving bundle links for collection {collection_id}: {e}", exc_info=True)
        # Continue to fallback method even on general errors
    
    # Fallback approach
    bundle_infos = get_bundle_structural_infos(collection)
    if bundle_infos:
        resolved_count, errors = resolve_links_using_structural_infos(bundle_infos)
        logger.info(f"Resolved {resolved_count} bundle links using fallback approach for collection ID: {collection_id}")
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during fallback resolution")
    else:
        logger.warning(f"No bundle structural infos found for collection {collection_id}. Could not resolve links.")
        
    # Return collection_id to pass down the pipeline regardless of success/failure
    return collection_id
