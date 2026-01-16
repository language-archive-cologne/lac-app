import logging
from typing import List, Dict, Optional, Tuple, Set, Any
from uuid import UUID

# Huey imports
from huey.contrib.djhuey import db_task, task, db_periodic_task
# Try importing configured Huey instance, fallback to default djhuey
try:
    from lacos.config.huey import HUEY as huey # Adjust if your Huey instance import path is different
except ImportError:
    from huey.contrib.djhuey import HUEY as huey
from huey import crontab, Huey # Remove Task import

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
def import_s3_collection(
    bucket: str, s3_key: str, update_existing: bool = False
) -> Optional[UUID]:
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
            collection = CollectionImporter.import_from_xml(
                xml_content,
                update_existing=update_existing,
            )

            fields_to_update: List[str] = []
            if getattr(collection, 'import_bucket', None) != bucket:
                collection.import_bucket = bucket
                fields_to_update.append('import_bucket')
            if getattr(collection, 'import_object_key', None) != s3_key:
                collection.import_object_key = s3_key
                fields_to_update.append('import_object_key')
            if fields_to_update:
                collection.save(update_fields=fields_to_update)

            collection_id = collection.id # Store ID for logging after commit
            collection_title = getattr(collection.general_info, 'display_title', 'Unknown') if hasattr(collection, 'general_info') else 'Unknown' # Safe access
            logger.info(f"COLLECTION IMPORT SUCCESS (within transaction): ID={collection_id} | Title={collection_title} | S3={s3_key}")
        
        # This part executes *after* the transaction successfully commits
        logger.info(f"COLLECTION COMMITTED: Transaction for collection {collection_id} | Title={collection_title} is now committed")
        return collection_id

    except Exception as e:
        logger.error(f"COLLECTION IMPORT FAILED: Error during import or transaction for S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

# --- Refactored Bundle Import Task ---
@db_task()
def import_s3_bundle(
    bucket: str, s3_key: str, update_existing: bool = False
) -> Optional[Tuple[UUID, UUID]]:
    """
    Import a single bundle from S3.
    Assumes BundleImporter.import_from_xml is modified to return (Bundle, bundle_resources_id).

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the bundle XML file.

    Returns:
        Tuple (bundle_id, bundle_resources_id) if successful, None otherwise.
    """
    task_id = f"BUNDLE-{s3_key.split('/')[-1]}"
    logger.info(f"{task_id}: Starting import from S3: {bucket}/{s3_key}")
    
    discovery_service = FileDiscoveryService()
    try:
        xml_content_bytes = discovery_service.read_s3_object(bucket, s3_key)
        if xml_content_bytes is None:
            logger.error(f"{task_id}: FAILED - XML not found or unreadable at {bucket}/{s3_key}")
            return None

        xml_content = xml_content_bytes.decode('utf-8')
        
        importer_result = BundleImporter.import_from_xml(
            xml_content,
            update_existing=update_existing,
        )

        if not importer_result or not isinstance(importer_result, tuple) or len(importer_result) != 2:
            logger.error(f"{task_id}: FAILED - BundleImporter did not return expected (bundle, bundle_resources_id) tuple.")
            return None
            
        bundle, bundle_resources_id = importer_result
        
        if not bundle or not bundle_resources_id:
             logger.error(f"{task_id}: FAILED - BundleImporter returned None for bundle or bundle_resources_id.")
             return None

        fields_to_update: List[str] = []
        if getattr(bundle, 'import_bucket', None) != bucket:
            bundle.import_bucket = bucket
            fields_to_update.append('import_bucket')
        if getattr(bundle, 'import_object_key', None) != s3_key:
            bundle.import_object_key = s3_key
            fields_to_update.append('import_object_key')
        if fields_to_update:
            bundle.save(update_fields=fields_to_update)

        bundle_title = getattr(bundle.general_info, 'display_title', 'Unknown') if hasattr(bundle, 'general_info') and bundle.general_info else 'Unknown'
        struct_info = bundle.structural_info.first() if hasattr(bundle, 'structural_info') else None
        collection_id_linked = getattr(struct_info.is_member_of_collection, 'id', 'None') if struct_info and hasattr(struct_info, 'is_member_of_collection') else 'None'
        
        logger.info(f"{task_id}: IMPORT SUCCESS | Bundle ID={bundle.id} | BundleResources ID={bundle_resources_id} | Collection ID={collection_id_linked} | Title={bundle_title}")
        return (bundle.id, bundle_resources_id)
        
    except Exception as e:
        logger.error(f"{task_id}: IMPORT FAILED - Error importing bundle from S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

# --- Refactored Bundle Group Import Task ---
@db_task()
def import_s3_bundles_for_collection(
    collection_id: Optional[UUID],
    bundle_keys: List[str],
    bucket: str,
    update_existing: bool = False,
) -> Tuple[Optional[UUID], List[Tuple[UUID, UUID]]]:
    """
    Task to import a list of bundles for a collection ID.
    Collects (bundle_id, bundle_resources_id) pairs for successful imports.

    Args:
        collection_id: The database ID of the collection (result from previous task).
        bundle_keys: A list of S3 keys for the bundle XML files.
        bucket: The S3 bucket where the bundles reside.

    Returns:
        Tuple (collection_id, list_of_successful_pairs)
        where list_of_successful_pairs contains (bundle_id, bundle_resources_id).
    """
    task_id = f"BUNDLE-GROUP-{collection_id}"
    successful_pairs: List[Tuple[UUID, UUID]] = []

    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided.")
        return (None, successful_pairs)

    # Verify collection exists
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown') if hasattr(collection, 'general_info') and collection.general_info else 'Unknown'
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found. Bundles cannot be reliably linked.")
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    if not bundle_keys:
        logger.info(f"{task_id}: No bundle keys provided for collection {collection_id}. Nothing to import.")
        return (collection_id, successful_pairs) # Return ID and empty list

    logger.info(f"{task_id}: Processing {len(bundle_keys)} bundle keys for collection ID={collection_id}")

    imported_count = 0
    failed_count = 0
    
    for index, bundle_key in enumerate(bundle_keys):
        bundle_task_id = f"{task_id}-BUNDLE-{index+1}"
        logger.info(f"{bundle_task_id}: Processing bundle {index+1}/{len(bundle_keys)} | S3 key: {bundle_key}")
        try:
            # Call single bundle import locally
            bundle_result = import_s3_bundle.call_local(
                bucket=bucket,
                s3_key=bundle_key,
                update_existing=update_existing,
            )
            
            if bundle_result and isinstance(bundle_result, tuple) and len(bundle_result) == 2:
                bundle_id, bundle_resources_id = bundle_result
                if bundle_id and bundle_resources_id:
                    imported_count += 1
                    successful_pairs.append(bundle_result) # Add the (id, id) pair
                    logger.info(f"{bundle_task_id}: SUCCESS - Bundle imported | ID={bundle_id} | ResourcesID={bundle_resources_id}")
                else:
                    failed_count += 1
                    logger.warning(f"{bundle_task_id}: FAILED - Bundle import returned None in tuple.")
            else:
                failed_count += 1
                logger.warning(f"{bundle_task_id}: FAILED - Bundle import returned None or invalid format.")
        except Exception as e:
            logger.error(f"{bundle_task_id}: FAILED - Error importing bundle: {e}", exc_info=True)
            failed_count += 1

    if imported_count > 0:
        logger.info(f"{task_id}: SUMMARY - Successfully imported {imported_count}/{len(bundle_keys)} bundles | Failed: {failed_count}")
        logger.debug(f"{task_id}: Successful pairs: {successful_pairs}")
    else:
        logger.warning(f"{task_id}: NO BUNDLES IMPORTED - All {failed_count} bundle imports failed for collection {collection_id}")

    logger.info(f"{task_id}: Returning collection ID={collection_id} and {len(successful_pairs)} successful pairs.")
    return (collection_id, successful_pairs)

# --- Refactored Link Resolution Task ---
@db_task()
def resolve_collection_bundle_links_task(collection_id: Optional[UUID], list_of_pairs: List[Tuple[UUID, UUID]]) -> Tuple[Optional[UUID], List[Tuple[UUID, UUID]]]:
    """
    Resolve CollectionMemberReferences. Passes the bundle pairs through.

    Args:
        collection_id: The ID of the collection.
        list_of_pairs: The list of (bundle_id, bundle_resources_id) from the previous task.

    Returns:
        The same Tuple (collection_id, list_of_successful_pairs).
    """
    task_id = f"RESOLVE-LINKS-{collection_id}"
    
    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided")
        return (None, list_of_pairs)  # Pass through existing list

    logger.info(f"{task_id}: Starting bundle link resolution for collection ID={collection_id}")

    # Verify collection exists
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown') if hasattr(collection, 'general_info') and collection.general_info else 'Unknown'
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found in database")
        return (collection_id, list_of_pairs) # Return original input
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    try:
        logger.info(f"{task_id}: Calling resolve_links_service for collection ID={collection_id}")
        result = resolve_links_service(collection_id) # Service only needs collection_id
        
        if result is None:
            logger.error(f"{task_id}: FAILED - resolve_links_service returned None for collection {collection_id}")
        else:
            try:
                from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
                linked_bundles = BundleStructuralInfo.objects.filter(is_member_of_collection_id=collection_id)
                bundle_count = linked_bundles.count()
                logger.info(f"{task_id}: Collection has {bundle_count} linked bundles after resolution")
            except Exception as e:
                logger.warning(f"{task_id}: Could not retrieve linked bundles for logging: {e}")
            
        logger.info(f"{task_id}: SUCCESS - Bundle link resolution completed for collection ID={collection_id}")
        
    except Exception as e:
        logger.error(f"{task_id}: FAILED - Error resolving bundle links for collection {collection_id}: {e}", exc_info=True)

    return (collection_id, list_of_pairs) # Always return the tuple

# --- Refactored Resource Mapping Task ---
@db_task()
def map_collection_resources(collection_id: Optional[UUID], list_of_pairs: List[Tuple[UUID, UUID]]) -> Optional[UUID]:
    """
    Create S3ResourceLocation entries for a collection and its bundles/resources.
    Uses the explicitly passed list of (bundle_id, bundle_resources_id) pairs.

    Args:
        collection_id: The ID of the collection.
        list_of_pairs: The list of (bundle_id, bundle_resources_id) from the previous task.

    Returns:
        The collection_id if successful, otherwise None.
    """
    task_id = f"MAP-RESOURCES-{collection_id}"
    
    if collection_id is None:
        logger.warning(f"{task_id}: SKIPPED - No collection ID provided")
        return None # Propagate None

    logger.info(f"{task_id}: Starting S3 resource mapping for collection ID={collection_id} using {len(list_of_pairs)} bundle/resources pairs.")

    # Verify collection exists
    try:
        from lacos.blam.models.collection.collection_repository import Collection
        collection = Collection.objects.get(id=collection_id)
        collection_title = getattr(collection.general_info, 'display_title', 'Unknown') if hasattr(collection, 'general_info') and collection.general_info else 'Unknown'
        logger.info(f"{task_id}: Verified collection exists | ID={collection_id} | Title={collection_title}")
    except Collection.DoesNotExist:
        logger.error(f"{task_id}: FAILED - Collection {collection_id} not found in database")
        return None
    except Exception as e:
        logger.warning(f"{task_id}: Warning - Error verifying collection {collection_id}: {e}")

    try:
        mapping_service = ResourceMappingService()
        # Pass the explicitly received list of pairs to the service method
        logger.info(f"{task_id}: Calling map_collection_hierarchy for collection ID={collection_id} with {len(list_of_pairs)} pairs.")
        total_mapped = mapping_service.map_collection_hierarchy(collection_id=collection_id, bundle_resources_pairs=list_of_pairs)
        
        logger.info(f"{task_id}: SUCCESS - Mapped {total_mapped} objects/resources for collection ID={collection_id}")
        
        return collection_id
    except Exception as e:
        logger.error(f"{task_id}: FAILED - Error mapping resources for collection {collection_id}: {e}", exc_info=True)
        return None # Return None on mapping failure


# --- Refactored Orchestration Function ---
def process_s3_prefix(bucket: str = None, prefix: str = '', update_existing: bool = False):
    """
    Finds S3 candidates locally and enqueues processing pipelines.
    Passes data explicitly between tasks.
    """
    logger.info(f"Starting synchronous S3 candidate finding for: {bucket or 'default bucket'}/{prefix}")
    discovery_service = FileDiscoveryService()
    actual_bucket = bucket or discovery_service.production_bucket

    # 1. Find potential XML files locally
    try:
        candidates = find_s3_import_candidates.call_local(actual_bucket, prefix)
        logger.info(f"Locally found {len(candidates.get('potential_collection_xmls', []))} potential collections and {len(candidates.get('potential_bundle_xmls', []))} potential bundles in {actual_bucket}/{prefix}")
    except Exception as e:
        logger.error(f"Error finding S3 import candidates locally for {actual_bucket}/{prefix}: {e}", exc_info=True)
        return

    collection_xmls = candidates.get('potential_collection_xmls', [])
    bundle_xmls = candidates.get('potential_bundle_xmls', [])

    if not collection_xmls and not bundle_xmls:
        logger.info(f"No collection or bundle XMLs found to process in {actual_bucket}/{prefix}.")
        return

    # 2. Group bundle keys by inferred collection identifier
    bundles_by_collection_id: Dict[str, List[str]] = {}
    for bundle_key in bundle_xmls:
        try:
            parts = bundle_key.split('/')
            collection_identifier = parts[0] if len(parts) > 1 else None # Safer check
            if not collection_identifier:
                logger.warning(f"Could not infer collection identifier from bundle key: {bundle_key}. Skipping.")
                continue
            if collection_identifier not in bundles_by_collection_id:
                bundles_by_collection_id[collection_identifier] = []
            bundles_by_collection_id[collection_identifier].append(bundle_key)
        except Exception as e:
            logger.warning(f"Error inferring collection id from bundle key {bundle_key}: {e}")
            continue
    logger.info(f"Grouped bundles into {len(bundles_by_collection_id)} collection groups for prefix {prefix}.")

    # 3. Create and enqueue a pipeline for each collection
    logger.info(f"Creating and enqueuing import pipelines for {len(collection_xmls)} potential collection XMLs found in {prefix}...")
    pipelines_enqueued = 0
    for coll_key in collection_xmls:
        try:
            # Infer collection identifier
            parts = coll_key.split('/')
            collection_identifier = parts[0] if parts else None
            if not collection_identifier:
                 logger.warning(f"Could not infer collection identifier from key: {coll_key}. Skipping.")
                 continue

            associated_bundle_keys = bundles_by_collection_id.get(collection_identifier, [])
            logger.info(f"Pipeline for Collection {collection_identifier} (Key: {coll_key}) | Associated Bundles: {len(associated_bundle_keys)}")

            # --- Define Pipeline ---
            # Task 1: Import Collection -> returns collection_id
            if update_existing:
                p = import_s3_collection.s(
                    actual_bucket,
                    coll_key,
                    update_existing=True,
                )
            else:
                p = import_s3_collection.s(actual_bucket, coll_key)

            # Task 2: Import Bundles -> takes (collection_id, bundle_keys, bucket), returns (collection_id, list_of_pairs)
            if update_existing:
                p = p.then(
                    import_s3_bundles_for_collection.s(
                        bundle_keys=associated_bundle_keys,
                        bucket=actual_bucket,
                        update_existing=True,
                    )
                )
            else:
                p = p.then(
                    import_s3_bundles_for_collection.s(
                        bundle_keys=associated_bundle_keys,
                        bucket=actual_bucket,
                    )
                )

            # Task 3: Resolve Links -> Now accepts (collection_id, list_of_pairs), returns same
            p = p.then(resolve_collection_bundle_links_task.s())

            # Task 4: Map Resources -> Now accepts (collection_id, list_of_pairs), returns collection_id or None
            p = p.then(map_collection_resources.s())
            
            # --- Enqueue Pipeline ---
            # Enqueue the pipeline object returned by the chain of .then() calls
            result = huey.enqueue(p)
            
            if result:
                # Attempt to get ID, but handle potential AttributeError
                try:
                    task_id_str = str(result.id)
                except AttributeError:
                    task_id_str = repr(result) # Fallback to repr if no id
                logger.info(f"Enqueued pipeline start for collection {collection_identifier} (Key: {coll_key}). Root Task Result/ID (approx): {task_id_str}")
            else:
                 logger.warning(f"Huey enqueue call for collection {collection_identifier} returned {result}.")
            pipelines_enqueued += 1

        except Exception as e:
            logger.error(f"Error creating/enqueuing pipeline for collection key {coll_key}: {e}", exc_info=True)
            continue

    logger.info(f"Completed enqueuing {pipelines_enqueued} collection processing pipelines for S3 prefix: {actual_bucket}/{prefix}")
