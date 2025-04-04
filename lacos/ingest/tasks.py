import logging
from typing import List, Dict, Optional, Tuple, Set
from uuid import UUID

# Huey imports
from huey.contrib.djhuey import db_task, task, db_periodic_task
# Try importing configured Huey instance, fallback to default djhuey
try:
    from lacos.config.huey import HUEY as huey # Adjust if your Huey instance import path is different
except ImportError:
    from huey.contrib.djhuey import HUEY as huey
from huey import crontab, Huey  # Import Huey for pipeline creation

# Importers and Services
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.blam.services.resolve_links import resolve_collection_bundle_links as resolve_links_service
from django.conf import settings
from django.db import transaction # Import transaction

logger = logging.getLogger(__name__)


@task()
def find_s3_import_candidates(bucket: str = None, prefix: str = '') -> Dict[str, List[str]]:
    """
    Find potential collection and bundle XML files in an S3 prefix.

    Args:
        bucket: S3 bucket name (uses default if None).
        prefix: Prefix to search within.

    Returns:
        Dict with 'potential_collection_xmls' and 'potential_bundle_xmls' keys
        containing lists of S3 keys.
    """
    logger.info(f"Searching for import candidates in S3: {bucket or 'default bucket'}/{prefix}")
    discovery_service = FileDiscoveryService()
    try:
        # Use the specific method that finds both types based on configured patterns
        result = discovery_service.find_collection_and_bundle_xmls_s3(bucket, prefix)
        logger.info(f"Import candidate search completed. Found {len(result.get('potential_collection_xmls', []))} potential collections and {len(result.get('potential_bundle_xmls', []))} potential bundles.")
        return result
    except Exception as e:
        logger.error(f"Error finding import candidates in S3: {e}")
        # Return empty dict on error to avoid downstream failures
        return {'potential_collection_xmls': [], 'potential_bundle_xmls': []}

# Revert to db_task and use transaction.atomic
@db_task()
def import_s3_collection(bucket: str, s3_key: str) -> Optional[UUID]:
    """
    Import a single collection from an XML file stored in S3.
    Uses transaction.atomic to ensure commit before returning.

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the collection XML file.

    Returns:
        Collection database ID if successful, None otherwise.
    """
    logger.info(f"COLLECTION IMPORT: Starting import from S3: {bucket}/{s3_key}")
    discovery_service = FileDiscoveryService()
    collection_id = None
    collection_title = "Unknown"
    try:
        with transaction.atomic():
            xml_content_bytes = discovery_service.read_s3_object(bucket, s3_key)
            if xml_content_bytes is None:
                logger.error(f"COLLECTION IMPORT FAILED: XML not found or unreadable at {bucket}/{s3_key}")
                # Raising exception inside atomic block ensures rollback
                raise ValueError(f"XML not found at {bucket}/{s3_key}")

            xml_content = xml_content_bytes.decode('utf-8')
            # Use CollectionImporter to handle parsing and saving
            collection = CollectionImporter.import_from_xml(xml_content)
            collection_id = collection.id # Store ID for logging after commit
            collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
            logger.info(f"COLLECTION IMPORT SUCCESS (within transaction): ID={collection_id} | Title={collection_title} | S3={s3_key}")
        
        # This part executes *after* the transaction successfully commits
        logger.info(f"COLLECTION COMMITTED: Transaction for collection {collection_id} | Title={collection_title} is now committed")
        return collection_id

    except Exception as e:
        logger.error(f"COLLECTION IMPORT FAILED: Error during import or transaction for S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

@db_task()
def import_s3_bundle(bucket: str, s3_key: str, collection_id: UUID = None) -> Optional[UUID]:
    """
    Import a single bundle from an XML file stored in S3 and link to a collection.

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the bundle XML file.
        collection_id: The database ID (UUID) of the collection this bundle belongs to.
                       This is optional as bundles should find their own collection
                       based on references in the XML.

    Returns:
        Bundle database ID (UUID) if successful, None otherwise.
    """
    task_id = f"BUNDLE-{s3_key.split('/')[-1]}"
    logger.info(f"{task_id}: Starting import from S3: {bucket}/{s3_key} | Target collection: {collection_id or 'auto-detect'}")
    
    # First verify if collection_id exists and is accessible
    if collection_id:
        try:
            from lacos.blam.models.collection.collection_repository import Collection
            collection = Collection.objects.get(id=collection_id)
            collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
            logger.info(f"{task_id}: Verified target collection {collection_id} exists and is accessible | Title: {collection_title}")
        except Collection.DoesNotExist:
            logger.warning(f"{task_id}: Target collection {collection_id} not found in database - bundle may not link correctly")
        except Exception as e:
            logger.warning(f"{task_id}: Error verifying collection {collection_id}: {e}")
    
    discovery_service = FileDiscoveryService()
    try:
        xml_content_bytes = discovery_service.read_s3_object(bucket, s3_key)
        if xml_content_bytes is None:
            logger.error(f"{task_id}: FAILED - XML not found or unreadable at {bucket}/{s3_key}")
            return None

        xml_content = xml_content_bytes.decode('utf-8')
        
        # Import the bundle from XML without passing collection_id
        # The bundle will find its collection based on references in the XML
        bundle = BundleImporter.import_from_xml(xml_content)
        
        if not bundle:
            logger.error(f"{task_id}: FAILED - BundleImporter returned None")
            return None
            
        bundle_title = getattr(bundle.general_info, 'display_title', 'Unknown')
        logger.info(f"{task_id}: Successfully imported bundle | ID={bundle.id} | Title={bundle_title}")
        
        # Check if the bundle found its collection 
        original_collection = None
        if hasattr(bundle, 'structural_info') and bundle.structural_info and bundle.structural_info.is_member_of_collection:
            original_collection = bundle.structural_info.is_member_of_collection
            original_collection_title = getattr(original_collection.general_info, 'display_title', 'Unknown')
            logger.info(f"{task_id}: Bundle automatically linked to collection | Collection ID={original_collection.id} | Title={original_collection_title}")
        else:
            logger.info(f"{task_id}: Bundle did not automatically link to any collection")
        
        # If collection_id was provided and the bundle's structural_info exists but has no collection link,
        # we can set it explicitly as a fallback
        if collection_id and bundle and hasattr(bundle, 'structural_info') and bundle.structural_info:
            if not bundle.structural_info.is_member_of_collection:
                try:
                    from lacos.blam.models.collection.collection_repository import Collection
                    collection = Collection.objects.get(id=collection_id)
                    collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
                    bundle.structural_info.is_member_of_collection = collection
                    bundle.structural_info.save(update_fields=['is_member_of_collection'])
                    logger.info(f"{task_id}: LINK SUCCESS - Explicitly linked bundle to collection | Collection ID={collection_id} | Title={collection_title}")
                except Exception as e:
                    logger.warning(f"{task_id}: LINK FAILED - Could not link bundle {bundle.id} to collection {collection_id}: {e}")
            elif original_collection and original_collection.id != collection_id:
                logger.warning(f"{task_id}: LINK CONFLICT - Bundle linked to different collection {original_collection.id} than provided {collection_id}")
        
        logger.info(f"{task_id}: IMPORT SUCCESS | Bundle ID={bundle.id} | Collection ID={getattr(bundle.structural_info.is_member_of_collection, 'id', 'None') if hasattr(bundle, 'structural_info') and bundle.structural_info else 'None'}")
        return bundle.id
    except Exception as e:
        logger.error(f"{task_id}: IMPORT FAILED - Error importing bundle from S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

@db_task()
def import_s3_bundles_for_collection(collection_id: Optional[UUID], bundle_keys: List[str], bucket: str) -> Optional[UUID]:
    """
    Task to import a list of bundles associated with a specific collection ID.
    Designed to be used in a Huey pipeline after collection import.
    Receives the list of bundle keys found by the initial scan.

    Args:
        collection_id: The database ID of the collection (result from previous task).
        bundle_keys: A list of S3 keys for the bundle XML files.
        bucket: The S3 bucket where the bundles reside.

    Returns:
        The collection_id if successful or None if input collection_id was None.
    """
    task_id = f"BUNDLE-GROUP-{collection_id}"
    
    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided")
        return None # Propagate None

    # First verify collection exists in the database
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found in database. Bundle import will likely fail.")
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    if not bundle_keys:
        logger.info(f"{task_id}: No bundle keys provided for collection {collection_id}. Nothing to import.")
        # Instead of returning early, we'll continue with the pipeline - the collection may have bundle 
        # references that will be resolved in the next step
        return collection_id

    logger.info(f"{task_id}: Processing {len(bundle_keys)} bundle keys for collection ID={collection_id}")
    logger.debug(f"{task_id}: Bundle keys: {', '.join(bundle_keys)}")

    imported_count = 0
    failed_count = 0
    successful_bundle_ids = []
    
    for index, bundle_key in enumerate(bundle_keys):
        bundle_task_id = f"{task_id}-BUNDLE-{index+1}"
        logger.info(f"{bundle_task_id}: Processing bundle {index+1}/{len(bundle_keys)} | S3 key: {bundle_key}")
        try:
            # Call the single bundle import task directly, passing the collection_id
            # This allows bundles to link to the collection even if they don't have references
            bundle_id = import_s3_bundle.call_local(bucket=bucket, s3_key=bundle_key, collection_id=collection_id)
            if bundle_id:
                imported_count += 1
                successful_bundle_ids.append(str(bundle_id))
                logger.info(f"{bundle_task_id}: SUCCESS - Bundle imported | ID={bundle_id}")
            else:
                failed_count += 1
                logger.warning(f"{bundle_task_id}: FAILED - Bundle import returned None")
        except Exception as e:
            logger.error(f"{bundle_task_id}: FAILED - Error importing bundle: {e}", exc_info=True)
            failed_count += 1

    if imported_count > 0:
        logger.info(f"{task_id}: SUMMARY - Successfully imported {imported_count}/{len(bundle_keys)} bundles | Failed: {failed_count}")
        logger.info(f"{task_id}: Successful bundle IDs: {', '.join(successful_bundle_ids)}")
    else:
        logger.warning(f"{task_id}: NO BUNDLES IMPORTED - All {failed_count} bundle imports failed for collection {collection_id}")

    # Return collection_id to continue pipeline regardless of bundle import success/failure
    logger.info(f"{task_id}: Continuing pipeline with collection ID={collection_id}")
    return collection_id

@db_task()
def resolve_collection_bundle_links_task(collection_id: Optional[UUID]) -> Optional[UUID]:
    """
    Resolve CollectionMemberReferences to actual Bundles for a given Collection.
    Uses the resolve_collection_bundle_links function from the services module.

    Args:
        collection_id: The database ID of the collection to process.

    Returns:
        The collection_id to pass down the pipeline, or None if collection not found.
    """
    task_id = f"RESOLVE-LINKS-{collection_id}"
    
    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided")
        return None  # Propagate None if previous step failed

    logger.info(f"{task_id}: Starting bundle link resolution for collection ID={collection_id}")

    # First verify collection exists
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found in database")
        return None
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    try:
        # Call the service function
        logger.info(f"{task_id}: Calling resolve_links_service for collection ID={collection_id}")
        result = resolve_links_service(collection_id)
        
        if result is None:
            logger.error(f"{task_id}: FAILED - resolve_links_service returned None for collection {collection_id}")
            return None
            
        # Get current bundle links for logging
        try:
            from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
            linked_bundles = BundleStructuralInfo.objects.filter(is_member_of_collection_id=collection_id)
            bundle_count = linked_bundles.count()
            logger.info(f"{task_id}: Collection has {bundle_count} linked bundles after resolution")
            if bundle_count > 0:
                bundle_ids = [str(b.bundle.id) if hasattr(b, 'bundle') and b.bundle else "No bundle" for b in linked_bundles]
                logger.info(f"{task_id}: Linked bundle IDs: {', '.join(bundle_ids)}")
            else:
                logger.warning(f"{task_id}: No bundles are linked to collection {collection_id} after resolution")
        except Exception as e:
            logger.warning(f"{task_id}: Could not retrieve linked bundles for logging: {e}")
            
        logger.info(f"{task_id}: SUCCESS - Bundle link resolution completed for collection ID={collection_id}")
        return collection_id
    except Exception as e:
        logger.error(f"{task_id}: FAILED - Error resolving bundle links for collection {collection_id}: {e}", exc_info=True)
        # Return collection_id to continue pipeline even if this step fails
        return collection_id

@db_task()
def map_collection_resources(collection_id: Optional[UUID]) -> Optional[UUID]: # Return Optional[UUID] for pipeline consistency
    """
    Create S3ResourceLocation entries for a collection and its linked bundles/resources.

    Args:
        collection_id: The database ID of the collection to map.
    """
    task_id = f"MAP-RESOURCES-{collection_id}"
    
    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided")
        return None # Propagate None

    logger.info(f"{task_id}: Starting S3 resource mapping for collection ID={collection_id}")

    # First verify collection exists
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
        
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown')
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
        
        # Check for linked bundles
        linked_bundles = BundleStructuralInfo.objects.filter(is_member_of_collection_id=collection_id)
        bundle_count = linked_bundles.count()
        logger.info(f"{task_id}: Collection has {bundle_count} linked bundles to map")
        if bundle_count > 0:
            bundle_ids = [str(b.bundle.id) if hasattr(b, 'bundle') and b.bundle else "No bundle" for b in linked_bundles]
            logger.info(f"{task_id}: Bundles to map: {', '.join(bundle_ids)}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found in database")
        return None
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    try:
        # Delegate to the service method
        mapping_service = ResourceMappingService()
        logger.info(f"{task_id}: Calling map_collection_hierarchy for collection ID={collection_id}")
        total_mapped = mapping_service.map_collection_hierarchy(collection_id)
        
        logger.info(f"{task_id}: SUCCESS - Mapped {total_mapped} resources for collection ID={collection_id}")
        
        # Log detailed mapping results if possible
        try:
            from django.contrib.contenttypes.models import ContentType
            from lacos.storage.models.s3_resource_location import S3ResourceLocation
            
            collection_ct = ContentType.objects.get_for_model(Collection)
            collection_locations = S3ResourceLocation.objects.filter(
                content_type=collection_ct, 
                object_id=collection_id
            )
            
            if collection_locations.exists():
                location = collection_locations.first()
                logger.info(f"{task_id}: Collection mapped to {location.s3_bucket}/{location.s3_key}")
            else:
                logger.warning(f"{task_id}: No S3 location mapped for collection {collection_id}")
                
        except Exception as e:
            logger.warning(f"{task_id}: Error retrieving mapping details: {e}")
        
        return collection_id
    except Exception as e:
        logger.error(f"{task_id}: FAILED - Error mapping resources for collection {collection_id}: {e}", exc_info=True)
        # We return collection_id even on error to allow pipeline to continue
        return collection_id



# or be called locally by another task.
def process_s3_prefix(bucket: str = None, prefix: str = ''):
    """
    Finds S3 candidates locally and enqueues processing pipelines for each collection.
    This function runs synchronously in the context of its caller.

    Args:
        bucket: S3 bucket name (uses default if None).
        prefix: Prefix to process.
    """
    logger.info(f"Starting synchronous S3 candidate finding for: {bucket or 'default bucket'}/{prefix}")
    discovery_service = FileDiscoveryService() # Instantiate once
    actual_bucket = bucket or discovery_service.production_bucket # Get default bucket if needed

    # 1. Find potential XML files *locally* within this function's execution context
    try:
        # Use call_local() to execute the task synchronously and get the result directly
        candidates = find_s3_import_candidates.call_local(actual_bucket, prefix)
        logger.info(f"Locally found {len(candidates.get('potential_collection_xmls', []))} potential collections and {len(candidates.get('potential_bundle_xmls', []))} potential bundles in {actual_bucket}/{prefix}")
    except Exception as e:
        logger.error(f"Error finding S3 import candidates locally for {actual_bucket}/{prefix}: {e}", exc_info=True)
        return # Stop processing if candidate finding fails

    # 2. Get the actual lists of keys from the candidates dict
    collection_xmls = candidates.get('potential_collection_xmls', [])
    bundle_xmls = candidates.get('potential_bundle_xmls', [])

    if not collection_xmls and not bundle_xmls:
        logger.info(f"No collection or bundle XMLs found to process in {actual_bucket}/{prefix} after local discovery.")
        return

    # 3. Group bundle keys by inferred collection identifier
    bundles_by_collection_id: Dict[str, List[str]] = {}
    logger.info(f"Grouping {len(bundle_xmls)} potential bundle XMLs by collection identifier for prefix {prefix}...")
    for bundle_key in bundle_xmls:
        try:
            # Using discovery service logic if available, otherwise fallback
            # This part needs robust implementation based on actual patterns
            parts = bundle_key.split('/')
            if len(parts) > 0:
                collection_identifier = parts[0] # Simplistic assumption
            else:
                collection_identifier = None

            if not collection_identifier:
                logger.warning(f"Could not infer collection identifier from bundle key: {bundle_key}. Skipping bundle.")
                continue

            if collection_identifier not in bundles_by_collection_id:
                bundles_by_collection_id[collection_identifier] = []
            bundles_by_collection_id[collection_identifier].append(bundle_key)

        except Exception as e: # Catch potential errors during inference
            logger.warning(f"Error inferring collection identifier from bundle key structure: {bundle_key}. Skipping. Error: {e}")
            continue
    logger.info(f"Grouped bundles into {len(bundles_by_collection_id)} collection groups for prefix {prefix}.")

    # 4. Create and enqueue a nested pipeline for each collection
    logger.info(f"Creating and enqueuing import pipelines for {len(collection_xmls)} potential collection XMLs found in {prefix}...")
    pipelines_enqueued = 0
    for coll_key in collection_xmls:
        try:
            # Infer collection identifier from the collection key
            # This needs to be robust based on your actual collection XML path pattern
            # Example: Assuming pattern is {collection_id}/v1/content/{collection_id}.xml
            parts = coll_key.split('/')
            collection_identifier = parts[0] if parts else None
            # Alternatively, use regex or FileDiscoveryService logic if paths are complex

            if not collection_identifier:
                 logger.warning(f"Could not infer collection identifier from key: {coll_key}. Skipping pipeline creation.")
                 continue

            # Get associated bundle keys for this collection identifier
            associated_bundle_keys = bundles_by_collection_id.get(collection_identifier, [])
            logger.info(f"Collection {collection_identifier} (Key: {coll_key}) has {len(associated_bundle_keys)} associated bundles to process.")

            # Create the task instance for the first step using the standard task
            first_task_in_pipeline = import_s3_collection.s(actual_bucket, coll_key)

            # --- Prepare arguments for import_s3_bundles_for_collection ---
            # We need to pass collection_id (result of first task), bundle_keys, and bucket.
            # Since the pipeline only passes the result, we need to bind the other args.
            # Create a signature for the second task with the necessary arguments bound.
            bundles_task_signature = import_s3_bundles_for_collection.s(
                bundle_keys=associated_bundle_keys,
                bucket=actual_bucket
            )

            # Chain the subsequent tasks onto the first task instance.
            # Note: import_s3_bundles_for_collection now expects (collection_id, bundle_keys, bucket)
            # The collection_id comes from the previous task, bundle_keys and bucket are bound.
            first_task_in_pipeline.then(bundles_task_signature)\
                                .then(resolve_collection_bundle_links_task)\
                                .then(map_collection_resources)

            # Enqueue the *first* task instance, which now contains the full pipeline definition.
            result = huey.enqueue(first_task_in_pipeline)
            # Log the enqueue attempt safely, without assuming result.id exists
            if result:
                # If result is not None or False, assume enqueue was likely successful
                # We can try logging result.id if needed later, but avoid it for now
                logger.info(f"Enqueued nested pipeline start for collection {collection_identifier} (Key: {coll_key}).")
            else:
                 logger.warning(f"Huey enqueue call for collection {collection_identifier} (Key: {coll_key}) returned {result}. Pipeline might not have been enqueued.")

            pipelines_enqueued += 1

        except Exception as e:
            logger.error(f"Error creating/enqueuing nested pipeline for collection key {coll_key}: {e}", exc_info=True)
            continue

    logger.info(f"Completed enqueuing {pipelines_enqueued} nested collection processing pipelines for S3 prefix: {actual_bucket}/{prefix}")


