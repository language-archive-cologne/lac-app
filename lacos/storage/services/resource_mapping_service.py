from django.contrib.contenttypes.models import ContentType
from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.models.acl_permissions import ACLPermissions
from .base_storage_service import BaseStorageService
import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from datetime import datetime, timedelta
import logging
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleResources, MediaResource, WrittenResource, OtherResource
from uuid import UUID
from typing import List, Dict, Optional, Tuple, Any
from django.db import transaction

logger = logging.getLogger(__name__)

class ResourceMappingService(BaseStorageService):
    """
    Service for managing the mapping between resources and their S3 storage locations.
    
    This service handles mapping between Django model objects (Collection, Bundle, Resources)
    and their corresponding locations in S3 storage.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ResourceMappingService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the ResourceMappingService with base storage configuration.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        logger.info("ResourceMappingService initialized")
        self.initialized = True
    
    def construct_s3_path(self, obj):
        """
        Construct the appropriate S3 path for an object based on its type.
        
        Args:
            obj: A Django model instance (Collection, Bundle, or Resource)
            
        Returns:
            str: The S3 path for the object, or None if the path can't be determined
        """
        # Import here placed at top level to avoid potential runtime issues
        
        if isinstance(obj, Collection):
            # Use UUID for path consistency
            return f'collections/{obj.id}/'
            
        elif isinstance(obj, Bundle):
            # Ensure structural_info and collection link exist
            if obj.structural_info.exists():
                si = obj.structural_info.first()
                if si.is_member_of_collection:
                    collection = si.is_member_of_collection
                    # Use UUIDs for path consistency
                    return f'collections/{collection.id}/bundles/{obj.id}/'
            
            logger.warning("Bundle is missing structural info or collection link, cannot construct S3 path", extra={"bundle_id": obj.id})
            return None
                
        # --- Corrected Logic for Resource Types --- 
        elif isinstance(obj, (MediaResource, WrittenResource, OtherResource)):
            bundle = None
            try:
                # Get the BundleResources container(s) via the reverse M2M.
                bundle_resources_container = obj.bundleresources_set.first()
                
                # Debug logging
                logger.info("Resource lookup", extra={"resource_type": type(obj).__name__, "resource_id": obj.id})
                logger.info("BundleResources containers", extra={"count": obj.bundleresources_set.count()})
                if bundle_resources_container:
                    logger.info("First container found", extra={"container_id": bundle_resources_container.id, "bundle_id": bundle_resources_container.bundle_id})

                if bundle_resources_container:
                    # Directly access the bundle via the foreign key
                    bundle = bundle_resources_container.bundle
                    logger.info("Found bundle", extra={"bundle_id": bundle.id if bundle else None})
                    
                    # Get structural info if it exists
                    if bundle:
                        logger.info("Bundle structural_info count", extra={"count": bundle.structural_info.count()})
                        si = bundle.structural_info.first()
                        if si:
                            logger.info("StructInfo collection", extra={"collection_id": si.is_member_of_collection_id})
                            collection = si.is_member_of_collection
                            if collection and hasattr(obj, 'file_name') and obj.file_name:
                                # Use UUIDs for path consistency
                                return f'collections/{collection.id}/bundles/{bundle.id}/resources/{obj.file_name}'

            except Exception as e: # Catch broader exceptions during traversal/query
                 # Handle cases where relations might not exist or query fails
                 logger.warning("Could not find related Bundle for resource, check model relations", extra={"resource_type": type(obj).__name__, "resource_id": obj.id, "error": str(e)}, exc_info=False)
                 bundle = None # Ensure bundle is None if any step failed
                 
            # Only if relationships are correctly detected but somehow invalid, we'll reach this section
            if bundle and hasattr(obj, 'file_name') and obj.file_name:
                # Find collection through structural_info
                si = bundle.structural_info.first()
                if si and si.is_member_of_collection:
                    collection = si.is_member_of_collection
                    # Use UUIDs for path consistency
                    return f'collections/{collection.id}/bundles/{bundle.id}/resources/{obj.file_name}'
                
            # Log if bundle couldn't be determined for a resource type object
            logger.warning("Failed to determine valid Bundle/Collection path for resource", extra={"resource_type": type(obj).__name__, "resource_id": obj.id})
            return None
                 
        else:
            # Default case if object type is not recognized
            logger.warning("Cannot construct S3 path for unrecognized object type", extra={"obj_type": type(obj).__name__})
            return None
    
    def get_s3_location(self, obj):
        """Get S3 location for any object (Collection, Bundle, or Resource)"""
        try:
            ct = ContentType.objects.get_for_model(obj)
            location = S3ResourceLocation.objects.get(
                content_type=ct,
                object_id=obj.id
            )
            return location
        except S3ResourceLocation.DoesNotExist:
            return None
    
    def resolve_pid_to_s3(self, pid_url):
        """Resolve a PID URL to an S3 location"""
        if not pid_url:
            return None

        normalized = str(pid_url).strip()
        if not normalized:
            return None

        candidates = {normalized}

        def _suffix_from_handle(value: str) -> Optional[str]:
            if value.startswith("hdl:"):
                return value[4:]
            marker = "hdl.handle.net/"
            if marker in value:
                return value.split(marker, 1)[1].lstrip("/")
            return None

        suffix = _suffix_from_handle(normalized)
        if suffix:
            candidates.add(f"hdl:{suffix}")
            candidates.add(f"https://hdl.handle.net/{suffix}")
            candidates.add(f"http://hdl.handle.net/{suffix}")

        location = S3ResourceLocation.objects.filter(
            resource_pid__in=list(candidates)
        ).first()
        return location
    
    def register_s3_location(self, obj, bucket, key=None, pid_url=None, fetch_metadata=True):
        """
        Register S3 location for an object

        Args:
            obj: The object to register (Collection, Bundle, or Resource)
            bucket: S3 bucket name
            key: S3 object key (if None, will be constructed from the object)
            pid_url: PID URL (if None, will try to use obj.file_pid)
            fetch_metadata: Controls S3 metadata fetching:
                - True (default): Fetch size_bytes/mime_type if missing
                - False: Skip metadata fetching entirely
                - 'force': Always fetch and update metadata

        Returns:
            S3ResourceLocation: The created or updated location
        """
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(obj)

        # If no key provided, try to construct it
        if key is None:
            key = self.construct_s3_path(obj)
            if key is None:
                raise ValueError(f"Could not construct S3 path for {obj}. Please provide a key.")

        # If no PID URL provided but object has file_pid, use that
        if pid_url is None and hasattr(obj, 'file_pid'):
            pid_url = obj.file_pid

        logger.info("register_s3_location", extra={"obj_type": type(obj).__name__, "obj_id": obj.id, "bucket": bucket, "key": key, "pid_url": pid_url})

        # Determine if this is a real file (resource) vs a prefix (collection/bundle)
        is_file_resource = isinstance(obj, (MediaResource, WrittenResource, OtherResource))

        # Create or update S3 location
        # Use resource_pid as lookup key if available (since it has unique constraint)
        # This ensures we update the existing record even if object_id changed
        if pid_url:
            location, created = S3ResourceLocation.objects.update_or_create(
                resource_pid=pid_url,
                defaults={
                    'content_type': ct,
                    'object_id': obj.id,
                    's3_bucket': bucket,
                    's3_key': key
                }
            )
            logger.info("register_s3_location completed", extra={"action": "CREATED" if created else "UPDATED", "location_id": location.id, "pid_url": pid_url})
        else:
            # Fall back to content_type + object_id for objects without PID
            location, created = S3ResourceLocation.objects.update_or_create(
                content_type=ct,
                object_id=obj.id,
                defaults={
                    'resource_pid': pid_url,
                    's3_bucket': bucket,
                    's3_key': key
                }
            )
            logger.info("register_s3_location completed", extra={"action": "CREATED" if created else "UPDATED", "location_id": location.id, "content_type": str(ct), "object_id": obj.id})

        # Fetch S3 metadata (size_bytes, mime_type) for file resources
        if fetch_metadata and is_file_resource:
            should_fetch = (
                fetch_metadata == 'force' or
                location.size_bytes is None or
                location.mime_type is None
            )
            if should_fetch:
                self._fetch_and_update_s3_metadata(location, bucket, key)

        return location

    def _fetch_and_update_s3_metadata(self, location, bucket, key):
        """
        Fetch size and content type from S3 and update the location record.

        Only updates fields if head_object succeeds - does not wipe existing
        metadata on failure.
        """
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            size_bytes = response.get('ContentLength')
            mime_type = response.get('ContentType')

            update_fields = []
            if size_bytes is not None:
                location.size_bytes = size_bytes
                update_fields.append('size_bytes')
            if mime_type:
                location.mime_type = mime_type
                update_fields.append('mime_type')

            if update_fields:
                location.save(update_fields=update_fields)
                logger.debug("Updated S3 metadata", extra={"key": key, "size_bytes": size_bytes, "mime_type": mime_type})

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                logger.debug("S3 object not found for metadata", extra={"bucket": bucket, "key": key})
            else:
                logger.warning("Failed to fetch S3 metadata", extra={"bucket": bucket, "key": key, "error": str(e)})
        except Exception as e:
            logger.warning("Unexpected error fetching S3 metadata", extra={"bucket": bucket, "key": key, "error": str(e)})
    
    def generate_presigned_url(self, bucket, key, expires_in=None, response_headers=None):
        """Generate a presigned URL for temporary access.

        Args:
            bucket: S3 bucket name
            key: S3 object key
            expires_in: URL expiration in seconds (default from settings.PRESIGNED_URL_EXPIRATION)
            response_headers: Optional dict with response headers (Content-Disposition, etc.)

        Returns:
            str: Presigned URL for GET access to the object
        """
        if expires_in is None:
            expires_in = getattr(settings, 'PRESIGNED_URL_EXPIRATION', 3600)

        params = {
            'Bucket': bucket,
            'Key': key
        }
        if response_headers:
            params.update(response_headers)

        url = self.get_presigned_client().generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expires_in
        )
        return url

    def get_resource_url(self, resource):
        """Get a presigned URL for a resource"""
        location = self.get_s3_location(resource)
        if not location:
            raise ValueError(f"No S3 location found for resource: {resource}")
        return self.generate_presigned_url(location.s3_bucket, location.s3_key)
    
    def get_resource_url_by_pid(self, pid):
        """Get a presigned URL for a resource by its PID"""
        location = self.resolve_pid_to_s3(pid)
        if not location:
            raise ValueError(f"No S3 location found for PID: {pid}")
        return self.generate_presigned_url(location.s3_bucket, location.s3_key)
        
    def batch_register_resources(self, resources, bucket, base_key):
        """Register multiple resources in a batch"""
        for resource in resources:
            # Extract the last part of the PID as a file name if no file_name is available
            if hasattr(resource, 'file_pid'):
                file_name = resource.file_pid.split('/')[-1]
                s3_key = f"{base_key}/{file_name}"
                self.register_s3_location(resource, bucket, s3_key)

    def _extract_ocfl_base_path(self, import_object_key: Optional[str]) -> Optional[str]:
        """
        Extract the base OCFL path from an import_object_key.

        The import_object_key format is:
        - OCFL 1.1: "{collection_folder}/v1/metadata/{collection_folder}.xml"
        - Legacy: "{collection_folder}/v1/content/{collection_folder}.xml"
        - Bundle OCFL 1.1: "{collection_folder}/{bundle_folder}/v1/metadata/{bundle_folder}.xml"
        - Bundle Legacy: "{collection_folder}/{bundle_folder}/v1/content/{bundle_folder}.xml"

        This method extracts everything before '/v1/' to get the base path.

        Args:
            import_object_key: The import_object_key from a Collection or Bundle

        Returns:
            The base OCFL path (e.g., "qaqet_child_language/" or "qaqet_child_language/bundle1/")
            or None if the path cannot be extracted
        """
        if not import_object_key:
            return None

        # OCFL 1.1: metadata in /v1/metadata/
        v1_metadata_marker = '/v1/metadata/'
        idx = import_object_key.find(v1_metadata_marker)
        if idx > 0:
            base_path = import_object_key[:idx] + '/'
            return base_path

        # Legacy: metadata in /v1/content/
        v1_content_marker = '/v1/content/'
        idx = import_object_key.find(v1_content_marker)
        if idx > 0:
            base_path = import_object_key[:idx] + '/'
            return base_path

        # Generic fallback: find /v1/ marker
        v1_marker = '/v1/'
        idx = import_object_key.find(v1_marker)
        if idx > 0:
            base_path = import_object_key[:idx] + '/'
            return base_path

        # Fallback: if no v1 marker, try to extract directory path
        # This handles cases where import_object_key might just be a directory
        if '/' in import_object_key:
            # Remove trailing filename if present
            parts = import_object_key.rsplit('/', 1)
            if '.' in parts[-1]:  # Has file extension, so last part is a filename
                return parts[0] + '/'
            return import_object_key.rstrip('/') + '/'

        return None

    def _get_ocfl_additional_metadata_base_path(self, import_object_key: Optional[str]) -> Optional[str]:
        """
        Get the base path for additional metadata files within an OCFL object.

        Additional metadata files are stored at: {object_path}/v1/metadata/additional_metadata/
        """
        if not import_object_key:
            return None
        base_path = self._extract_ocfl_base_path(import_object_key)
        if base_path:
            return base_path.rstrip('/') + '/v1/metadata/additional_metadata/'
        return None

    def _get_ocfl_resource_base_path(self, bundle_import_object_key: Optional[str]) -> Optional[str]:
        """
        Get the base path for resources within a bundle's OCFL structure.

        OCFL 1.1 structure: Resources are stored at: {bundle_path}/v1/content/
        Legacy structure: Resources were at: {bundle_path}/v1/content/Resources/

        Args:
            bundle_import_object_key: The import_object_key from a Bundle

        Returns:
            The base path for resources (e.g., "qaqet_child_language/bundle1/v1/content/")
            or None if the path cannot be extracted
        """
        if not bundle_import_object_key:
            return None

        # Extract base path first
        base_path = self._extract_ocfl_base_path(bundle_import_object_key)
        if base_path:
            # OCFL 1.1: resources directly in v1/content/ (no Resources subdirectory)
            return base_path.rstrip('/') + '/v1/content/'

        return None

    def map_collection_hierarchy(
        self,
        collection_id: UUID,
        bundle_resources_pairs: Optional[List[Tuple[UUID, Optional[UUID]]]] = None,
    ) -> int:
        """
        Map an entire collection hierarchy to S3 locations.
        Uses explicitly passed (bundle_id, bundle_resources_id) pairs.

        Uses actual OCFL paths from import_object_key instead of UUID-based paths
        to ensure presigned URLs point to where the data actually exists in S3.

        Args:
            collection_id: The collection UUID to map
            bundle_resources_pairs: List of tuples (bundle_id, bundle_resources_id or None)

        Returns:
            int: Total number of objects mapped (Collection + Bundles + Resources)
        """
        from lacos.storage.services.file_discovery_service import FileDiscoveryService

        total_mapped = 0
        discovery_service = FileDiscoveryService()

        # 1. Map the Collection object itself
        try:
            collection = Collection.objects.get(id=collection_id)

            # Use collection's import_bucket if available, otherwise fall back to production_bucket
            # This ensures presigned URLs point to where the data actually exists
            bucket = collection.import_bucket if collection.import_bucket else discovery_service.production_bucket
            logger.info("map_collection_hierarchy", extra={"collection_id": collection_id})
            logger.info("map_collection_hierarchy import_bucket", extra={"import_bucket": collection.import_bucket})
            logger.info("map_collection_hierarchy import_object_key", extra={"import_object_key": collection.import_object_key})
            logger.info("map_collection_hierarchy using bucket", extra={"bucket": bucket})

            # Use actual OCFL path from import_object_key instead of UUID-based path
            collection_key_prefix = self._extract_ocfl_base_path(collection.import_object_key)
            if not collection_key_prefix:
                # Fallback to UUID-based path if import_object_key is not set
                collection_key_prefix = discovery_service.form_collection_path(collection_id) + "/"
                logger.warning("Collection has no import_object_key, falling back to UUID-based path", extra={"collection_id": collection_id, "collection_key_prefix": collection_key_prefix})

            self.register_s3_location(collection, bucket, collection_key_prefix)
            logger.info("Mapped Collection to S3 location", extra={"collection_id": collection_id, "bucket": bucket, "key_prefix": collection_key_prefix})
            total_mapped += 1

            # 1.5 Map collection additional metadata files
            structural_info = collection.structural_info.first()
            if structural_info:
                additional_metadata_files = structural_info.additional_metadata_files.all()
                if additional_metadata_files.exists():
                    collection_resources_base = self._get_ocfl_additional_metadata_base_path(collection.import_object_key)
                    if collection_resources_base:
                        metadata_count = 0
                        for metadata_file in additional_metadata_files:
                            if hasattr(metadata_file, 'file_name') and metadata_file.file_name:
                                try:
                                    resource_s3_key = f"{collection_resources_base}{metadata_file.file_name}"
                                    self.register_s3_location(metadata_file, bucket, resource_s3_key)
                                    metadata_count += 1
                                    total_mapped += 1
                                except Exception as meta_map_e:
                                    logger.error("Failed to map collection metadata file", extra={"metadata_file_id": getattr(metadata_file, 'id', 'N/A'), "file_name": metadata_file.file_name, "error": str(meta_map_e)}, exc_info=False)
                        logger.info("Mapped additional metadata files for Collection", extra={"count": metadata_count, "collection_id": collection_id})
                    else:
                        logger.warning("Collection has no import_object_key, cannot map additional metadata files", extra={"collection_id": collection_id})

        except Collection.DoesNotExist:
             logger.error("Collection not found for resource mapping", extra={"collection_id": collection_id})
             return 0 # Cannot proceed without collection
        except Exception as e:
            logger.error("Failed to map Collection object", extra={"collection_id": collection_id, "error": str(e)}, exc_info=True)
            # Continue to map bundles even if collection mapping failed?
            # For now, we return 0 if collection fetch fails, but log error if mapping fails.

        if bundle_resources_pairs is None:
            bundle_resources_pairs = []
            bundles = Bundle.objects.filter(structural_info__is_member_of_collection=collection)
            for bundle in bundles:
                resources = bundle.resources.first()
                bundle_resources_pairs.append((bundle.id, resources.id if resources else None))

        # 2. Iterate through bundles using the provided pairs
        logger.info("Processing bundle/resources pairs for collection", extra={"count": len(bundle_resources_pairs), "collection_id": collection_id})
        for bundle_id, bundle_resources_id in bundle_resources_pairs:
            try:
                # Fetch Bundle by ID
                bundle = Bundle.objects.get(id=bundle_id)

                # Use actual OCFL path from import_object_key instead of UUID-based path
                bundle_key_prefix = self._extract_ocfl_base_path(bundle.import_object_key)
                if not bundle_key_prefix:
                    # Fallback to UUID-based path if import_object_key is not set
                    bundle_key_prefix = discovery_service.form_bundle_path(collection_id, bundle.id) + "/"
                    logger.warning("Bundle has no import_object_key, falling back to UUID-based path", extra={"bundle_id": bundle.id, "bundle_key_prefix": bundle_key_prefix})

                self.register_s3_location(bundle, bucket, bundle_key_prefix)
                logger.info("Mapped Bundle to S3 location", extra={"bundle_id": bundle.id, "bucket": bucket, "key_prefix": bundle_key_prefix})
                total_mapped += 1

                # Derive the base key for bundle files once so both additional
                # metadata files and regular resources use the same OCFL location.
                resources_base_key = self._get_ocfl_resource_base_path(bundle.import_object_key)
                if not resources_base_key:
                    try:
                        resource_pattern = discovery_service.get_resource_path_pattern()
                        prefix_pattern = resource_pattern.rsplit('{resource_filename}', 1)[0]
                        resources_base_key = prefix_pattern.format(
                            collection_id=collection_id,
                            bundle_id=bundle.id,
                        )
                        logger.warning(
                            "Bundle has no import_object_key, falling back to UUID-based resource path",
                            extra={"bundle_id": bundle.id, "resources_base_key": resources_base_key},
                        )
                    except Exception as format_e:
                        logger.error(
                            "Could not format resource base key for bundle",
                            extra={"bundle_id": bundle.id, "error": str(format_e)},
                        )
                        resources_base_key = None

                # 2.5 Map bundle additional metadata files.
                structural_info = bundle.structural_info.first()
                additional_metadata_base_key = self._get_ocfl_additional_metadata_base_path(bundle.import_object_key)
                if structural_info and additional_metadata_base_key:
                    metadata_count = 0
                    for metadata_file in structural_info.additional_metadata_files.all():
                        if hasattr(metadata_file, 'file_name') and metadata_file.file_name:
                            try:
                                resource_s3_key = f"{additional_metadata_base_key}{metadata_file.file_name}"
                                self.register_s3_location(metadata_file, bucket, resource_s3_key)
                                metadata_count += 1
                                total_mapped += 1
                            except Exception as meta_map_e:
                                logger.error(
                                    "Failed to map bundle metadata file",
                                    extra={"metadata_file_id": getattr(metadata_file, 'id', 'N/A'), "file_name": metadata_file.file_name, "error": str(meta_map_e)},
                                    exc_info=False,
                                )
                    if metadata_count:
                        logger.info(
                            "Mapped additional metadata files for Bundle",
                            extra={"count": metadata_count, "bundle_id": bundle.id},
                        )

                # 3. Map Resources using the BundleResources ID
                if bundle_resources_id:
                    try:
                        # Fetch BundleResources directly by its ID
                        bundle_resources = BundleResources.objects.get(id=bundle_resources_id)
                        logger.info("Found BundleResources object for Bundle via passed ID", extra={"bundle_resources_id": bundle_resources.id, "bundle_id": bundle.id})

                        if not resources_base_key:
                            logger.warning(
                                "No resources base path available for Bundle, skipping resource mapping",
                                extra={"bundle_id": bundle.id},
                            )
                            continue

                        resource_count = 0
                        # Map media resources
                        if hasattr(bundle_resources, 'bundle_media_resources'):
                            for media_resource in bundle_resources.bundle_media_resources.all():
                                if hasattr(media_resource, 'file_name') and media_resource.file_name:
                                    try:
                                        resource_s3_key = f"{resources_base_key}{media_resource.file_name}"
                                        self.register_s3_location(media_resource, bucket, resource_s3_key)
                                        resource_count += 1
                                        total_mapped += 1
                                    except Exception as res_map_e:
                                        logger.error("Failed to map media resource", extra={"resource_id": getattr(media_resource, 'id', 'N/A'), "file_name": media_resource.file_name, "error": str(res_map_e)}, exc_info=False)

                        # Map written resources
                        if hasattr(bundle_resources, 'bundle_written_resources'):
                             for written_resource in bundle_resources.bundle_written_resources.all():
                                if hasattr(written_resource, 'file_name') and written_resource.file_name:
                                    try:
                                        resource_s3_key = f"{resources_base_key}{written_resource.file_name}"
                                        self.register_s3_location(written_resource, bucket, resource_s3_key)
                                        resource_count += 1
                                        total_mapped += 1
                                    except Exception as res_map_e:
                                        logger.error("Failed to map written resource", extra={"resource_id": getattr(written_resource, 'id', 'N/A'), "file_name": written_resource.file_name, "error": str(res_map_e)}, exc_info=False)

                        # Map other resources
                        if hasattr(bundle_resources, 'bundle_other_resources'):
                             for other_resource in bundle_resources.bundle_other_resources.all():
                                if hasattr(other_resource, 'file_name') and other_resource.file_name:
                                    try:
                                        resource_s3_key = f"{resources_base_key}{other_resource.file_name}"
                                        self.register_s3_location(other_resource, bucket, resource_s3_key)
                                        resource_count += 1
                                        total_mapped += 1
                                    except Exception as res_map_e:
                                        logger.error("Failed to map other resource", extra={"resource_id": getattr(other_resource, 'id', 'N/A'), "file_name": other_resource.file_name, "error": str(res_map_e)}, exc_info=False)

                        logger.info("Mapped resources for bundle", extra={"resource_count": resource_count, "bundle_id": bundle.id, "bundle_resources_id": bundle_resources.id})

                    except BundleResources.DoesNotExist:
                         logger.error("BundleResources object not found, cannot map resources", extra={"bundle_resources_id": bundle_resources_id, "bundle_id": bundle.id})
                    except Exception as res_fetch_e:
                         logger.error("Error fetching or processing BundleResources", extra={"bundle_resources_id": bundle_resources_id, "bundle_id": bundle.id, "error": str(res_fetch_e)}, exc_info=True)
                else:
                    logger.warning("No BundleResources ID provided for bundle, skipping resource mapping", extra={"bundle_id": bundle.id})

            except Bundle.DoesNotExist:
                logger.error("Bundle not found, cannot map bundle or its resources", extra={"bundle_id": bundle_id})
            except Exception as bundle_map_e:
                logger.error("Failed to map bundle or its resources", extra={"bundle_id": bundle_id, "error": str(bundle_map_e)}, exc_info=True)

        logger.info("Finished mapping for collection", extra={"collection_id": collection_id, "total_mapped": total_mapped})
        return total_mapped  # Return count of mapped objects


# For backwards compatibility, create an alias
S3Service = ResourceMappingService


class ACFLService:
    @staticmethod
    def get_permissions(obj):
        """Get ACFL permissions for any object (Collection or Bundle)"""
        try:
            ct = ContentType.objects.get_for_model(obj)
            permissions = ACLPermissions.objects.get(
                content_type=ct,
                object_id=obj.id
            )
            return permissions
        except ACLPermissions.DoesNotExist:
            return None
    
    @staticmethod
    def create_permissions(obj, bucket, key, permissions_data=None):
        """Create ACFL permissions for an object"""
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(obj)
        
        # Create permissions
        permissions, created = ACLPermissions.objects.update_or_create(
            content_type=ct,
            object_id=obj.id,
            defaults={
                'ACL_file_bucket': bucket,
                'ACL_file_key': key,
                'permissions_data': permissions_data,
                'last_synced': datetime.now() if permissions_data else None
            }
        )
        return permissions
    
    @staticmethod
    def check_permission(user, obj, permission_type='read'):
        """
        Check if user has permission on an object
        
        Args:
            user: Django user
            obj: Collection, Bundle, or Resource instance
            permission_type: Type of permission to check
            
        Returns:
            bool: Whether user has permission
        """
        # First check object-specific permissions
        permissions = ACFLService.get_permissions(obj)
        if permissions and permissions.permissions_data:
            has_permission = ACFLService._check_acfl_permission(
                user, 
                permissions.permissions_data, 
                permission_type
            )
            if has_permission is not None:  # If explicitly granted or denied
                return has_permission
        
        # If no explicit permission or inheritance is enabled, check parent
        # Import here to avoid circular imports
        from lacos.blam.models.bundle.bundle_repository import Bundle
        
        # For bundles, check collection permissions
        if isinstance(obj, Bundle) and hasattr(obj, 'structural_info') and hasattr(obj.structural_info, 'is_member_of_collection'):
            collection = obj.structural_info.is_member_of_collection
            return ACFLService.check_permission(user, collection, permission_type)
        
        # For resources, check bundle permissions
        # This depends on how resources are related to bundles in your model
        if hasattr(obj, 'file_name') and hasattr(obj, 'file_pid'):
            bundle = None
            
            # Check if the resource has a direct reference to a bundle
            if hasattr(obj, 'bundle'):
                bundle = obj.bundle
            # Check if the resource is part of bundle_media_resources
            elif hasattr(obj, 'mediaresource') and hasattr(obj.mediaresource, 'bundle_media_resources'):
                for bundle_resources in obj.mediaresource.bundle_media_resources.all():
                    bundle = bundle_resources.bundle
                    break
            # Check if the resource is part of bundle_written_resources
            elif hasattr(obj, 'writtenresource') and hasattr(obj.writtenresource, 'bundle_written_resources'):
                for bundle_resources in obj.writtenresource.bundle_written_resources.all():
                    bundle = bundle_resources.bundle
                    break
            # Check if the resource is part of bundle_other_resources
            elif hasattr(obj, 'otherresource') and hasattr(obj.otherresource, 'bundle_other_resources'):
                for bundle_resources in obj.otherresource.bundle_other_resources.all():
                    bundle = bundle_resources.bundle
                    break
            
            if bundle:
                return ACFLService.check_permission(user, bundle, permission_type)
        
        # Default deny if no permissions found and no parent to check
        return False
    
    @staticmethod
    def _check_acfl_permission(user, acfl_data, permission_type):
        """
        Check if user has permission according to ACFL data
        
        This is a placeholder - implement based on your ACFL structure
        """
        # Example implementation - adjust to your ACFL structure
        if 'permissions' not in acfl_data:
            return None
        
        for perm in acfl_data['permissions']:
            if perm.get('type') == permission_type:
                # Check if user is in allowed users
                if 'users' in perm and user.username in perm['users']:
                    return True
                
                # Check if user is in allowed groups
                if 'groups' in perm:
                    user_groups = set(user.groups.values_list('name', flat=True))
                    if any(group in user_groups for group in perm['groups']):
                        return True
        
        return False
    
    @staticmethod
    def refresh_permissions(obj):
        """Refresh ACFL permissions from S3"""
        permissions = ACFLService.get_permissions(obj)
        if not permissions:
            return None
        
        # Get the ACFL file from S3
        resource_mapping_service = ResourceMappingService()
        s3_client = resource_mapping_service.s3_client
        
        try:
            response = s3_client.get_object(
                Bucket=permissions.ACL_file_bucket,
                Key=permissions.ACL_file_key
            )
            acfl_data = response['Body'].read().decode('utf-8')
            
            # Parse the ACFL data (assuming JSON format)
            import json
            permissions_data = json.loads(acfl_data)
            
            # Update the permissions
            permissions.permissions_data = permissions_data
            permissions.last_synced = datetime.now()
            permissions.save()
            
            return permissions
        except Exception as e:
            # Log the error
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Error refreshing ACFL permissions", extra={"error": str(e)})
            return None
