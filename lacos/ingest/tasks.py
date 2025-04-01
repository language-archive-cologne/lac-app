import logging
from typing import List, Dict, Optional, Tuple, Set

# Huey imports
from huey.contrib.djhuey import db_task, task, db_periodic_task
from huey import crontab

# Importers and Services
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.services.file_discovery_service import FileDiscoveryService

# Django settings and models (import models within tasks to avoid circular issues)
from django.conf import settings

logger = logging.getLogger(__name__)

# --- S3 Specific Tasks ---

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
def import_s3_collection(bucket: str, s3_key: str) -> Optional[int]:
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
def import_s3_bundle(bucket: str, s3_key: str, collection_id: int) -> Optional[int]:
    """
    Import a single bundle from an XML file stored in S3 and link to a collection.

    Args:
        bucket: S3 bucket name.
        s3_key: S3 key for the bundle XML file.
        collection_id: The database ID of the collection this bundle belongs to.

    Returns:
        Bundle database ID if successful, None otherwise.
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
        bundle = BundleImporter.import_from_xml(xml_content, collection_id)
        logger.info(f"Successfully imported bundle ID: {bundle.id} from S3 key: {s3_key} for collection {collection_id}")
        return bundle.id
    except Exception as e:
        logger.error(f"Error importing bundle from S3 {bucket}/{s3_key}: {e}", exc_info=True)
        return None

@db_task()
def resolve_collection_bundle_links(collection_id: int) -> Optional[int]:
    """
    Resolve CollectionMemberReferences to actual Bundles for a given Collection.

    Args:
        collection_id: The database ID of the collection to process.

    Returns:
        Number of bundle references resolved, or None if collection not found.
    """
    from lacos.blam.models.collection.collection_repository import Collection
    logger.info(f"Attempting to resolve bundle links for collection ID: {collection_id}")
    try:
        collection = Collection.objects.get(id=collection_id)
        resolved_count = CollectionImporter.resolve_bundle_references(collection)
        logger.info(f"Resolved {resolved_count} bundle links for collection ID: {collection_id}")
        return resolved_count
    except Collection.DoesNotExist:
        logger.error(f"Collection {collection_id} not found for resolving bundle links.")
        return None
    except Exception as e:
        logger.error(f"Error resolving bundle links for collection {collection_id}: {e}", exc_info=True)
        return None # Indicate error

@db_task()
def map_collection_resources(collection_id: int):
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
            mapping_service.register_s3_location(collection, bucket, collection_key_prefix)
            logger.info(f"Mapped Collection {collection_id} to S3 location: {bucket}/{collection_key_prefix}")
        except Exception as e:
             logger.error(f"Failed to map Collection {collection_id} object: {e}", exc_info=True)


        # 2. Map associated Bundles and their Resources
        # Ensure bundle links have been resolved before running this
        if hasattr(collection, 'structural_info') and collection.structural_info:
            # Assuming 'members' gives CollectionMemberReference, and 'bundle' is the resolved link
            linked_bundles = Bundle.objects.filter(structural_info__members__collection_structural_info=collection.structural_info, structural_info__members__bundle__isnull=False).distinct()

            logger.info(f"Found {linked_bundles.count()} linked bundles to map for collection {collection_id}.")

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


# --- Orchestration Tasks ---

@task()
def process_s3_prefix(bucket: str = None, prefix: str = ''):
    """
    Master task to process finds in an S3 prefix: find, import, link, map.

    Args:
        bucket: S3 bucket name (uses default if None).
        prefix: Prefix to process.
    """
    logger.info(f"Starting S3 processing for: {bucket or 'default bucket'}/{prefix}")
    actual_bucket = bucket or FileDiscoveryService().production_bucket # Get default bucket if needed

    # 1. Find potential XML files
    candidates = find_s3_import_candidates(actual_bucket, prefix)
    collection_xmls = candidates.get('potential_collection_xmls', [])
    bundle_xmls = candidates.get('potential_bundle_xmls', [])

    if not collection_xmls and not bundle_xmls:
        logger.info(f"No collection or bundle XMLs found to process in {actual_bucket}/{prefix}.")
        return

    # 2. Import Collections and store their DB IDs mapped to their string identifier
    imported_collections_map: Dict[str, int] = {} # Maps string identifier -> db_id
    discovery_service = FileDiscoveryService() # For inferring identifiers

    logger.info(f"Found {len(collection_xmls)} potential collection XMLs. Starting import...")
    for coll_key in collection_xmls:
        # Infer collection identifier (e.g., 'algerien') from the key
        # This relies on the key matching the pattern used by form_collection_xml_path
        try:
            # Example inference: If key is 'algerien/algerien/v1/content/algerien.xml'
            # We assume the first part is the identifier. This needs robust implementation.
            # A safer way might be to parse the identifier *from* the XML content after reading.
            # Let's use a simple split for now, assuming pattern {id}/{id}/...
            collection_identifier = coll_key.split('/')[0] # Simplistic assumption
            if not collection_identifier:
                 logger.warning(f"Could not infer collection identifier from key: {coll_key}. Skipping.")
                 continue
        except IndexError:
            logger.warning(f"Could not infer collection identifier from key structure: {coll_key}. Skipping.")
            continue

        collection_db_id = import_s3_collection(actual_bucket, coll_key)
        if collection_db_id:
            imported_collections_map[collection_identifier] = collection_db_id
            logger.info(f"Successfully launched import task for collection {collection_identifier} (Key: {coll_key}), DB ID: {collection_db_id}")
        else:
             logger.error(f"Import failed or returned no ID for collection key: {coll_key}")


    # 3. Import Bundles, linking them to already imported collections
    imported_bundle_ids: Dict[int, List[int]] = {} # Maps collection_db_id -> list[bundle_db_id]

    logger.info(f"Found {len(bundle_xmls)} potential bundle XMLs. Starting import...")
    for bundle_key in bundle_xmls:
         # Infer collection identifier from the bundle key
         # Assumes pattern {collection_id}/{bundle_id}/...
         try:
             collection_identifier = bundle_key.split('/')[0] # Simplistic assumption
             if not collection_identifier:
                  logger.warning(f"Could not infer collection identifier from bundle key: {bundle_key}. Skipping bundle.")
                  continue
         except IndexError:
             logger.warning(f"Could not infer collection identifier from bundle key structure: {bundle_key}. Skipping bundle.")
             continue

         # Find the DB ID for the inferred collection identifier
         collection_db_id = imported_collections_map.get(collection_identifier)

         if collection_db_id:
             bundle_db_id = import_s3_bundle(actual_bucket, bundle_key, collection_db_id)
             if bundle_db_id:
                 if collection_db_id not in imported_bundle_ids:
                     imported_bundle_ids[collection_db_id] = []
                 imported_bundle_ids[collection_db_id].append(bundle_db_id)
                 logger.info(f"Successfully launched import task for bundle (Key: {bundle_key}), linked to Collection ID: {collection_db_id}, Bundle DB ID: {bundle_db_id}")
             else:
                  logger.error(f"Import failed or returned no ID for bundle key: {bundle_key}")

         else:
             logger.warning(f"Skipping bundle import for key {bundle_key}. Collection identifier '{collection_identifier}' was not successfully imported or identifier mismatch.")


    # 4. Resolve Bundle Links for imported collections
    logger.info(f"Triggering bundle link resolution for {len(imported_collections_map)} collections...")
    for collection_db_id in imported_collections_map.values():
        resolve_collection_bundle_links(collection_db_id)
        logger.info(f"Launched bundle link resolution task for Collection ID: {collection_db_id}")

    # 5. Map Resources for imported collections
    # This should run *after* linking is likely complete, though tasks might run in parallel.
    # Consider adding delays or using pipelines if strict ordering is needed.
    logger.info(f"Triggering resource mapping for {len(imported_collections_map)} collections...")
    for collection_db_id in imported_collections_map.values():
        map_collection_resources(collection_db_id)
        logger.info(f"Launched resource mapping task for Collection ID: {collection_db_id}")

    logger.info(f"Completed launching tasks for S3 prefix: {actual_bucket}/{prefix}")


