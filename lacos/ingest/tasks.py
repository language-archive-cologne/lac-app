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

# Django settings and models (import models within tasks to avoid circular issues)
from django.conf import settings

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

@db_task()
def import_s3_collection(bucket: str, s3_key: str) -> Optional[UUID]:
    """
    Import a single collection from an XML file stored in S3.

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the collection XML file.

    Returns:
        Collection database ID if successful, None otherwise.
    """
    logger.info(f"Importing collection from S3: {bucket}/{s3_key}")
    discovery_service = FileDiscoveryService()
    try:
        xml_content_bytes = discovery_service.read_s3_object(bucket, s3_key)
        if xml_content_bytes is None:
            logger.error(f"Collection XML not found or unreadable at {bucket}/{s3_key}")
            return None

        xml_content = xml_content_bytes.decode('utf-8')
        # Use CollectionImporter to handle parsing and saving
        collection = CollectionImporter.import_from_xml(xml_content)
        logger.info(f"Successfully imported collection ID: {collection.id} from S3 key: {s3_key}")
        return collection.id
    except Exception as e:
        # Catch specific validation errors?
        logger.error(f"Error importing collection from S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

@db_task()
def import_s3_bundle(bucket: str, s3_key: str, collection_id: UUID) -> Optional[UUID]:
    """
    Import a single bundle from an XML file stored in S3 and link to a collection.

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the bundle XML file.
        collection_id: The database ID (UUID) of the collection this bundle belongs to.

    Returns:
        Bundle database ID (UUID) if successful, None otherwise.
    """
    if not collection_id:
        logger.error(f"Cannot import bundle {s3_key} without a valid collection_id.")
        return None

    logger.info(f"Importing bundle from S3: {bucket}/{s3_key} for collection ID: {collection_id}")
    discovery_service = FileDiscoveryService()
    try:
        xml_content_bytes = discovery_service.read_s3_object(bucket, s3_key)
        if xml_content_bytes is None:
            logger.error(f"Bundle XML not found or unreadable at {bucket}/{s3_key}")
            return None

        xml_content = xml_content_bytes.decode('utf-8')
        # Use BundleImporter, passing the collection_id for linking
        # Assuming BundleImporter expects the collection_id
        # FIX: Call importer without collection_id UUID, it extracts info from XML
        bundle = BundleImporter.import_from_xml(xml_content)
        logger.info(f"Successfully imported bundle ID: {bundle.id} from S3 key: {s3_key} for collection {collection_id}")
        return bundle.id
    except Exception as e:
        logger.error(f"Error importing bundle from S3 {bucket}/{s3_key}: {e}", exc_info=True)
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
    if collection_id is None:
        logger.warning(f"Skipping bundle import as collection_id is None.")
        return None # Propagate None

    if not bundle_keys:
        logger.info(f"No bundle keys provided for collection {collection_id}. Nothing to import.")
        return collection_id

    logger.info(f"Received {len(bundle_keys)} bundle keys to import for collection ID: {collection_id}")

    imported_count = 0
    failed_count = 0
    for bundle_key in bundle_keys:
        try:
            # Call the single bundle import task directly (or enqueue if preferred)
            # Using call_local for simplicity here, assuming it's acceptable
            # If imports are long, enqueueing import_s3_bundle might be better
            bundle_id = import_s3_bundle.call_local(bucket=bucket, s3_key=bundle_key, collection_id=collection_id)
            if bundle_id:
                imported_count += 1
            else:
                failed_count += 1
        except Exception as e:
            logger.error(f"Error triggering import for bundle key {bundle_key}: {e}", exc_info=True)
            failed_count += 1

    logger.info(f"Bundle import process finished for collection {collection_id}. Imported: {imported_count}, Failed: {failed_count}")

    # Return collection_id to continue pipeline regardless of bundle import success/failure
    return collection_id

@db_task()
def resolve_collection_bundle_links(collection_id: Optional[UUID]) -> Optional[UUID]:
    """
    Resolve CollectionMemberReferences to actual Bundles for a given Collection.

    Args:
        collection_id: The database ID of the collection to process.

    Returns:
        The collection_id to pass down the pipeline, or None if collection not found.
    """
    from lacos.blam.models.collection.collection_repository import Collection
    logger.info(f"Attempting to resolve bundle links for collection ID: {collection_id}")

    if collection_id is None:
        logger.warning("resolve_collection_bundle_links received None collection_id. Skipping.")
        return None # Propagate None if previous step failed

    try:
        collection = Collection.objects.get(id=collection_id)
        
        # Try to resolve bundle references in a more robust way
        try:
            resolved_count = CollectionImporter.resolve_bundle_references(collection)
            logger.info(f"Resolved {resolved_count} bundle links for collection ID: {collection_id}")
        except AttributeError as e:
            # Handle the case where collection.structural_info doesn't have members attribute
            logger.warning(f"Could not resolve bundle links using standard method: {e}. Using alternate approach.")
            
            # Try an alternate approach using the model relationships directly
            resolved_count = 0
            try:
                # Use the related_name defined in BundleStructuralInfo
                bundle_structural_infos = collection.bundle_collection.all()
                logger.info(f"Found {len(bundle_structural_infos)} bundle structural infos using 'collection.bundle_collection'")
                
                # Process these members to link bundles
                for member_info in bundle_structural_infos:
                    # Assuming the logic should be applied to the BundleStructuralInfo object itself
                    # or potentially the Bundle it links to (if member_info.resolve_bundle exists)
                    if hasattr(member_info, 'resolve_bundle'):
                        if member_info.resolve_bundle():
                            resolved_count += 1
                    else:
                        # If resolve_bundle is not on BundleStructuralInfo, maybe it's on the Bundle?
                        # This assumes BundleStructuralInfo has a link back to Bundle named 'bundle'
                        if hasattr(member_info, 'bundle') and hasattr(member_info.bundle, 'resolve_bundle'):
                           if member_info.bundle.resolve_bundle():
                               resolved_count += 1
                        else:
                           logger.warning(f"Could not find a 'resolve_bundle' method for BundleStructuralInfo {getattr(member_info, 'id', 'N/A')} or its related Bundle.")

            except Exception as alt_e:
                 logger.error(f"Error occurred during alternate bundle resolution: {alt_e}", exc_info=True)
            
            logger.info(f"Resolved {resolved_count} bundle links using alternate approach for collection ID: {collection_id}")
        
        # Return collection_id to pass down the pipeline
        return collection_id
    except Collection.DoesNotExist:
        logger.error(f"Collection {collection_id} not found for resolving bundle links.")
        return None
    except Exception as e:
        logger.error(f"Error resolving bundle links for collection {collection_id}: {e}", exc_info=True)
        return collection_id  # Return ID to continue pipeline even if this step fails

@db_task()
def map_collection_resources(collection_id: Optional[UUID]) -> Optional[UUID]: # Return Optional[UUID] for pipeline consistency
    """
    Create S3ResourceLocation entries for a collection and its linked bundles/resources.

    Args:
        collection_id: The database ID of the collection to map.
    """
    from lacos.blam.models.collection.collection_repository import Collection
    from lacos.blam.models.bundle.bundle_repository import Bundle
    # Import specific resource models if needed for detailed mapping
    # from lacos.blam.models.resource import MediaResource, WrittenResource, OtherResource

    logger.info(f"Mapping S3 resources for collection ID: {collection_id}")

    if collection_id is None:
        logger.warning("map_collection_resources received None collection_id. Skipping.")
        return None # Propagate None

    mapping_service = ResourceMappingService()
    discovery_service = FileDiscoveryService() # Needed for path formatting

    try:
        collection = Collection.objects.get(id=collection_id)

        # 1. Map the Collection object itself
        try:
            # Use FileDiscoveryService to get the expected S3 *prefix* (key) for the collection
            # Assuming collection path pattern refers to a prefix ending in '/'
            collection_key_prefix = discovery_service.form_collection_path(collection_id) + "/" # Ensure trailing slash if needed
            # Bucket usually comes from settings or service default
            bucket = discovery_service.production_bucket
            try:
                mapping_service.register_s3_location(collection, bucket, collection_key_prefix)
                logger.info(f"Mapped Collection {collection_id} to S3 location: {bucket}/{collection_key_prefix}")
            except Exception as register_err:
                # Handle integer overflow or other database errors
                logger.error(f"Failed to map Collection {collection_id} to S3 due to database error: {register_err}", exc_info=True)
                # We'll continue with bundle mapping even if collection mapping fails
        except Exception as e:
             logger.error(f"Failed to map Collection {collection_id} object: {e}", exc_info=True)


        # 2. Map associated Bundles and their Resources
        # Ensure bundle links have been resolved before running this
        if hasattr(collection, 'structural_info') and collection.structural_info:
            try:
                # Use the reverse relationship from Collection to BundleStructuralInfo
                linked_bundles = Bundle.objects.filter(
                    structural_info__is_member_of_collection=collection
                ).distinct()
                
                logger.info(f"Found {linked_bundles.count()} linked bundles to map for collection {collection_id}.")
            except Exception as e:
                logger.warning(f"Error querying linked bundles with standard relationship: {e}")
                # If the above query fails, try a more direct approach
                try:
                    # Get bundles via the bundle_collection reverse relationship
                    linked_bundles = Bundle.objects.filter(
                        structural_info__in=collection.bundle_collection.all()
                    ).distinct()
                    logger.info(f"Found {linked_bundles.count()} linked bundles using bundle_collection reverse relation")
                except Exception as alt_e:
                    logger.error(f"Failed with alternative bundle lookup approach as well: {alt_e}")
                    linked_bundles = Bundle.objects.none()
            
            for bundle in linked_bundles:
                try:
                    # Map the Bundle object
                    bundle_key_prefix = discovery_service.form_bundle_path(collection_id, bundle.id) + "/" # Ensure trailing slash
                    mapping_service.register_s3_location(bundle, bucket, bundle_key_prefix)
                    logger.info(f"Mapped Bundle {bundle.id} to S3 location: {bucket}/{bundle_key_prefix}")

                    # 3. Map Resources within the Bundle (Example - adjust to your models)
                    # Construct the base resource key prefix
                    try:
                         resource_pattern = discovery_service.get_resource_path_pattern()
                         prefix_pattern = resource_pattern.rsplit('{resource_filename}', 1)[0]
                         resources_base_key = prefix_pattern.format(collection_id=collection_id, bundle_id=bundle.id)
                    except Exception as format_e:
                        logger.error(f"Could not format resource base key for bundle {bundle.id}: {format_e}")
                        continue # Skip resource mapping for this bundle

                    resource_count = 0
                    # Iterate through different resource types linked to the bundle
                    # Example: assumes related names like 'bundle_media_resources', etc.
                    resource_relations = ['bundle_media_resources', 'bundle_written_resources', 'bundle_other_resources']
                    for relation_name in resource_relations:
                        if hasattr(bundle, relation_name):
                             related_manager = getattr(bundle, relation_name)
                             if hasattr(related_manager, 'all'):
                                 for bundle_resource_link in related_manager.all():
                                     # Get the actual resource instance (MediaResource, WrittenResource...)
                                     # This assumes the link object has an attribute pointing to the actual resource
                                     resource = None
                                     if hasattr(bundle_resource_link, 'media_resource'):
                                         resource = bundle_resource_link.media_resource
                                     elif hasattr(bundle_resource_link, 'written_resource'):
                                         resource = bundle_resource_link.written_resource
                                     elif hasattr(bundle_resource_link, 'other_resource'):
                                         resource = bundle_resource_link.other_resource

                                     if resource and hasattr(resource, 'file_name'):
                                         try:
                                             # Construct full S3 key for the resource
                                             resource_s3_key = f"{resources_base_key}{resource.file_name}"
                                             mapping_service.register_s3_location(resource, bucket, resource_s3_key)
                                             resource_count += 1
                                         except Exception as res_map_e:
                                             logger.error(f"Failed to map resource {getattr(resource, 'id', 'N/A')} (name: {resource.file_name}) for bundle {bundle.id}: {res_map_e}", exc_info=True)
                                     else:
                                         logger.warning(f"Could not map resource linked via {relation_name} for bundle {bundle.id}: Missing resource object or file_name.")


                    logger.info(f"Mapped {resource_count} resources for Bundle {bundle.id}")

                except Exception as bundle_map_e:
                    logger.error(f"Failed to map Bundle {bundle.id} or its resources: {bundle_map_e}", exc_info=True)

    except Collection.DoesNotExist:
        logger.error(f"Collection {collection_id} not found for resource mapping.")
    except Exception as e:
        logger.error(f"Unexpected error mapping resources for collection {collection_id}: {e}", exc_info=True)
        return None # Propagate None or indicate error

    # Return collection_id for pipeline consistency if successful
    return collection_id


# --- Orchestration Tasks ---

# Removed @task() decorator - this function will now run synchronously
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

            # Create the task instance for the first step
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


