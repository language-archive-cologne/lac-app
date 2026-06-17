import logging
import json
from pathlib import Path
from typing import List, Dict, Union, Optional, Set, Any
from botocore.exceptions import ClientError

from django.conf import settings
from .base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)

class FileDiscoveryService(BaseStorageService):
    """
    Service for discovering files in directory structures.
    
    This service handles finding files based on patterns and crawling directory
    structures to identify resources.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FileDiscoveryService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        if hasattr(self, 'initialized'):
            return
        super().__init__(skip_bucket_check=skip_bucket_check)
        
        # Load path structure configuration from settings
        self.path_structure = self._load_path_structure()
        
        logger.info("FileDiscoveryService initialized with configured path patterns")
        self.initialized = True
    
    def _load_path_structure(self) -> Dict[str, Any]:
        """
        Load path structure configuration from settings.
        
        This method loads individual path pattern settings from Django settings and
        constructs derived paths to avoid duplication.
        
        Returns:
            Dictionary containing path structure configuration
        """
        path_structure = {}
        
        # Get base path patterns directly from settings with no defaults
        collection_path_pattern = getattr(settings, 'COLLECTION_PATH_PATTERN')
        path_structure['collection_path_pattern'] = collection_path_pattern
        
        bundle_path_pattern = getattr(settings, 'BUNDLE_PATH_PATTERN')
        path_structure['bundle_path_pattern'] = bundle_path_pattern
        
        # Resource path pattern - OCFL 1.1: resources in v1/content/ (versioned)
        resource_path_pattern = getattr(settings, 'RESOURCE_PATH_PATTERN', None)
        if resource_path_pattern is None:
            resource_path_pattern = bundle_path_pattern + '/v1/content/{resource_filename}'
        path_structure['resource_path_pattern'] = resource_path_pattern

        # XML file paths - OCFL 1.1: metadata in v1/metadata/ (not versioned)
        collection_xml_path = getattr(settings, 'COLLECTION_XML_PATH', None)
        if collection_xml_path is None:
            # Default derived from collection path - OCFL 1.1 places metadata outside content
            collection_xml_path = collection_path_pattern + '/v1/metadata/{collection_id}.xml'
        path_structure['collection_xml_path'] = collection_xml_path

        bundle_xml_path = getattr(settings, 'BUNDLE_XML_PATH', None)
        if bundle_xml_path is None:
            # Default derived from bundle path - OCFL 1.1 places metadata outside content
            bundle_xml_path = bundle_path_pattern + '/v1/metadata/{bundle_id}.xml'
        path_structure['bundle_xml_path'] = bundle_xml_path
        
        # Log the loaded configuration
        logger.info("Loaded path patterns", extra={"collection": collection_path_pattern, "bundle": bundle_path_pattern})
        logger.info("Derived paths", extra={"collection_xml": collection_xml_path, "bundle_xml": bundle_xml_path})
        
        return path_structure
    
    def get_collection_path_pattern(self) -> str:
        """Get the configured collection path pattern"""
        return self.path_structure.get('collection_path_pattern')
    
    def get_bundle_path_pattern(self) -> str:
        """Get the configured bundle path pattern"""
        return self.path_structure.get('bundle_path_pattern')
    
    def get_resource_path_pattern(self) -> str:
        """Get the configured resource path pattern"""
        return self.path_structure.get('resource_path_pattern')
    
    def get_collection_xml_path(self) -> str:
        """Get the configured collection XML path pattern"""
        return self.path_structure.get('collection_xml_path')
    
    def get_bundle_xml_path(self) -> str:
        """Get the configured bundle XML path pattern"""
        return self.path_structure.get('bundle_xml_path')
    
    def form_collection_path(self, collection_id: Union[str, int]) -> str:
        """
        Form an S3 path for a collection based on the configured pattern.
        
        Args:
            collection_id: Collection ID to use in the path
            
        Returns:
            Formatted S3 path for the collection
        """
        pattern = self.get_collection_path_pattern()
        return pattern.format(collection_id=collection_id)
    
    def form_bundle_path(self, collection_id: Union[str, int], bundle_id: Union[str, int]) -> str:
        """
        Form an S3 path for a bundle based on the configured pattern.
        
        Args:
            collection_id: Collection ID to use in the path
            bundle_id: Bundle ID to use in the path
            
        Returns:
            Formatted S3 path for the bundle
        """
        pattern = self.get_bundle_path_pattern()
        return pattern.format(collection_id=collection_id, bundle_id=bundle_id)
    
    def form_resource_path(self, collection_id: Union[str, int], bundle_id: Union[str, int], 
                          resource_filename: str) -> str:
        """
        Form an S3 path for a resource based on the configured pattern.
        
        Args:
            collection_id: Collection ID to use in the path
            bundle_id: Bundle ID to use in the path
            resource_filename: Filename of the resource
            
        Returns:
            Formatted S3 path for the resource
        """
        pattern = self.get_resource_path_pattern()
        return pattern.format(
            collection_id=collection_id,
            bundle_id=bundle_id,
            resource_filename=resource_filename
        )
    
    def form_collection_xml_path(self, collection_id: Union[str, int]) -> str:
        """
        Form the path to a collection's XML file based on the configured pattern.
        
        Args:
            collection_id: Collection ID to use in the path
            
        Returns:
            Formatted path for the collection XML file
        """
        pattern = self.get_collection_xml_path()
        return pattern.format(collection_id=collection_id)
    
    def form_bundle_xml_path(self, collection_id: Union[str, int], bundle_id: Union[str, int]) -> str:
        """
        Form the path to a bundle's XML file based on the configured pattern.
        
        Args:
            collection_id: Collection ID to use in the path
            bundle_id: Bundle ID to use in the path
            
        Returns:
            Formatted path for the bundle XML file
        """
        pattern = self.get_bundle_xml_path()
        return pattern.format(collection_id=collection_id, bundle_id=bundle_id)

    def find_collections_s3(self, bucket: str = None, prefix: str = "") -> List[str]:
        """
        Find all collection directories in the specified S3 bucket.
        
        A collection is identified as a top-level directory that contains
        the expected folder structure with an XML file matching the collection name.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            prefix: Prefix to start searching from
            
        Returns:
            List of collection IDs found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        collections = []
        
        try:
            # List all "directories" at the top level
            paginator = self.s3_client.get_paginator('list_objects_v2')
            response = paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter='/')
            
            for prefix_obj in response.search('CommonPrefixes'):
                dir_prefix = prefix_obj.get('Prefix')
                # Extract collection ID using string manipulation for S3 paths
                dir_name = dir_prefix.rstrip('/').rsplit('/', 1)[-1]
                
                # Check for the expected XML file using the configured path pattern
                collection_xml_key = self.form_collection_xml_path(dir_name)
                try:
                    self.s3_client.head_object(Bucket=bucket, Key=collection_xml_key)
                    collections.append(dir_name)
                    logger.debug("Found collection in S3", extra={"dir_name": dir_name})
                except Exception as e:
                    logger.debug("Not a collection or error", extra={"dir_name": dir_name, "error": str(e)})
            
            logger.info("Found collections in S3 bucket", extra={"count": len(collections), "bucket": bucket})
            return collections
        except Exception as e:
            logger.error("Error finding collections in S3", extra={"error": str(e)})
            return []

    def find_bundles_in_collection_s3(self, bucket: str = None, collection_id: str = None) -> List[str]:
        """
        Find all bundle directories within a collection directory in S3.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            collection_id: Collection ID to search in
            
        Returns:
            List of bundle IDs found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if collection_id is None:
            return []
            
        bundles = []
        collection_prefix = f"{collection_id}/"
        
        try:
            # List all "directories" within the collection
            paginator = self.s3_client.get_paginator('list_objects_v2')
            response = paginator.paginate(Bucket=bucket, Prefix=collection_prefix, Delimiter='/')
            
            for prefix_obj in response.search('CommonPrefixes'):
                dir_prefix = prefix_obj.get('Prefix')
                # Extract bundle ID using string manipulation for S3 paths
                bundle_id = dir_prefix.rstrip('/').rsplit('/', 1)[-1]
                
                # Skip if it's the same as the collection (inner folder with same name)
                if bundle_id == collection_id:
                    continue
                
                # Check for the expected XML file using the form_bundle_xml_path method
                bundle_xml_key = self.form_bundle_xml_path(collection_id, bundle_id)
                try:
                    self.s3_client.head_object(Bucket=bucket, Key=bundle_xml_key)
                    bundles.append(bundle_id)
                    logger.debug("Found bundle in S3", extra={"bundle_id": bundle_id, "collection_id": collection_id})
                except Exception as e:
                    logger.debug("Not a bundle or error", extra={"bundle_id": bundle_id, "error": str(e)})
            
            logger.info("Found bundles in collection", extra={"count": len(bundles), "collection_id": collection_id, "bucket": bucket})
            return bundles
        except Exception as e:
            logger.error("Error finding bundles in collection in S3", extra={"error": str(e)})
            return []

    def find_resources_in_bundle_s3(self, bucket: str = None, collection_id: str = None, bundle_id: str = None) -> List[str]:
        """
        Find all resources within a bundle directory in S3.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            collection_id: Collection ID containing the bundle
            bundle_id: Bundle ID to search in
            
        Returns:
            List of resource filenames found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if collection_id is None or bundle_id is None:
            return []
            
        resources = []
        
        # Construct the resources prefix directly from the pattern
        resource_pattern = self.get_resource_path_pattern()
        # Format the pattern up to the filename part
        try:
            prefix_pattern = resource_pattern.rsplit('{resource_filename}', 1)[0]
            resources_prefix = prefix_pattern.format(collection_id=collection_id, bundle_id=bundle_id)
        except KeyError: # Handle cases where format keys might be missing if pattern is unexpected
             logger.error("Could not format resource prefix from pattern", extra={"resource_pattern": resource_pattern})
             return []
        
        try:
            # List all files in the resources directory
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=resources_prefix)
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        key = obj['Key']
                        # Extract filename using string manipulation for S3 paths
                        filename = key.rsplit('/', 1)[-1]
                        if filename: # Avoid adding empty strings if key ends with /
                           # Ensure we only list direct children, not items in sub-prefixes
                           if key.startswith(resources_prefix) and '/' not in key[len(resources_prefix):]:
                               resources.append(filename)
                               logger.debug("Found resource in S3", extra={"file_name": filename, "bundle_id": bundle_id})
            
            logger.info("Found resources in bundle", extra={"count": len(resources), "bundle_id": bundle_id, "bucket": bucket})
            return resources
        except Exception as e:
            logger.error("Error finding resources in bundle in S3", extra={"error": str(e)})
            return []

    def find_collection_and_bundle_xmls_s3(self, bucket, prefix=""):
        """
        Find all collection and bundle XML files in the specified S3 bucket.
        Assumes collection and bundle directories are siblings under the prefix.
        Performs a single recursive listing and classifies keys locally to avoid
        issuing a HEAD request for every candidate XML path.
        
        Args:
            bucket: S3 bucket name
            prefix: Prefix containing the collection and bundle sibling directories
            
        Returns:
            Dictionary with lists of collection and bundle XML paths
        """
        logger.info(
            "Starting S3 XML discovery for collections",
            extra={"bucket": bucket, "prefix": prefix},
        )
        result = {
            'potential_collection_xmls': [],
            'potential_bundle_xmls': []
        }

        try:
            object_keys = self._list_s3_object_keys(bucket, prefix)
            result = self._discover_collection_and_bundle_xmls_from_keys(object_keys)
            if not result['potential_collection_xmls']:
                logger.warning(
                    "No collection XML found under prefix; skipping bundle discovery",
                    extra={"bucket": bucket, "prefix": prefix},
                )
        except Exception as outer_e:
            logger.error(
                "Failed during S3 listing for prefix",
                extra={"prefix": prefix, "error": str(outer_e)},
                exc_info=True,
            )

        logger.info(
            "Finished S3 XML discovery",
            extra={
                "collections_found": len(result['potential_collection_xmls']),
                "bundles_found": len(result['potential_bundle_xmls']),
            },
        )
        return result

    def _list_s3_object_keys(self, bucket: str, prefix: str = "") -> List[str]:
        paginator = self.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        keys = []
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj.get('Key')
                if key and key.endswith(".xml"):
                    keys.append(key)
        logger.debug(
            "Listed S3 object keys for XML discovery",
            extra={"bucket": bucket, "prefix": prefix, "count": len(keys)},
        )
        return keys

    def _discover_collection_and_bundle_xmls_from_keys(
        self,
        object_keys: List[str],
    ) -> Dict[str, List[str]]:
        result = {
            'potential_collection_xmls': [],
            'potential_bundle_xmls': []
        }
        collection_ids = []
        seen_collection_keys = set()

        for key in sorted(object_keys):
            collection_id = self._collection_id_from_xml_key(key)
            if not collection_id or key in seen_collection_keys:
                continue
            seen_collection_keys.add(key)
            collection_ids.append(collection_id)
            result['potential_collection_xmls'].append(key)
            logger.info(
                "Identified potential Collection via XML",
                extra={"collection_xml_key": key},
            )

        if not collection_ids:
            return result

        collection_key_set = set(result['potential_collection_xmls'])
        seen_bundle_keys = set()
        for key in sorted(object_keys):
            if key in collection_key_set or key in seen_bundle_keys:
                continue
            collection_id = self._bundle_collection_id_from_xml_key(key, collection_ids)
            if not collection_id:
                continue
            seen_bundle_keys.add(key)
            result['potential_bundle_xmls'].append(key)
            logger.info(
                "Identified Bundle via XML",
                extra={"bundle_xml_key": key, "collection_id": collection_id},
            )

        return result

    def _collection_id_from_xml_key(self, key: str) -> Optional[str]:
        xml_id = self._xml_filename_stem(key)
        if not xml_id:
            return None
        if self._matches_s3_key_tail(key, self.form_collection_xml_path(xml_id)):
            return xml_id
        return None

    def _bundle_collection_id_from_xml_key(
        self,
        key: str,
        collection_ids: List[str],
    ) -> Optional[str]:
        bundle_id = self._xml_filename_stem(key)
        if not bundle_id:
            return None
        for collection_id in collection_ids:
            if self._matches_s3_key_tail(
                key,
                self.form_bundle_xml_path(collection_id, bundle_id),
            ):
                return collection_id
        return None

    @staticmethod
    def _xml_filename_stem(key: str) -> Optional[str]:
        filename = key.rsplit("/", 1)[-1]
        if not filename.endswith(".xml") or filename == ".xml":
            return None
        return filename[:-4]

    @staticmethod
    def _matches_s3_key_tail(key: str, candidate_key: str) -> bool:
        normalized_key = key.strip("/")
        normalized_candidate = candidate_key.strip("/")
        return (
            normalized_key == normalized_candidate
            or normalized_key.endswith(f"/{normalized_candidate}")
        )

    def head_s3_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """
        Get S3 object metadata via HEAD request without downloading the object.

        Returns:
            Dict with 'ETag', 'ContentLength', 'LastModified', or None if not found.
        """
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            return {
                "ETag": response.get("ETag", "").strip('"'),
                "ContentLength": response.get("ContentLength"),
                "LastModified": response.get("LastModified"),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise

    def read_s3_object(self, bucket: str = None, key: str = None) -> Optional[bytes]:
        """
        Read the contents of an S3 object.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            key: S3 object key
            
        Returns:
            Object content as bytes, or None if the object doesn't exist
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if key is None:
            return None
            
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning("S3 object not found", extra={"bucket": bucket, "key": key})
                return None
            else:
                logger.error("Error reading S3 object", extra={"bucket": bucket, "key": key, "error": str(e)})
                raise

    def get_resource(self, bucket: str = None, collection_id: str = None, 
                   bundle_id: str = None, resource_filename: str = None) -> Optional[bytes]:
        """
        Get a specific resource by its path components.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            collection_id: Collection ID containing the resource
            bundle_id: Bundle ID containing the resource
            resource_filename: Filename of the resource
            
        Returns:
            Resource content as bytes, or None if not found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if not all([collection_id, bundle_id, resource_filename]):
            logger.error("Missing required parameters for resource retrieval")
            return None
            
        # Form the resource path
        resource_path = self.form_resource_path(collection_id, bundle_id, resource_filename)
        
        # Get the resource content
        return self.read_s3_object(bucket, resource_path)

    def get_collection_xml(self, bucket: str = None, collection_id: str = None) -> Optional[bytes]:
        """
        Get a collection's XML file content.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            collection_id: Collection ID
            
        Returns:
            XML content as bytes, or None if not found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if not collection_id:
            logger.error("Missing collection_id for collection XML retrieval")
            return None
            
        # Form the collection XML path
        xml_path = self.form_collection_xml_path(collection_id)
        
        # Get the XML content
        return self.read_s3_object(bucket, xml_path)
        
    def get_bundle_xml(self, bucket: str = None, collection_id: str = None, bundle_id: str = None) -> Optional[bytes]:
        """
        Get a bundle's XML file content.
        
        Args:
            bucket: S3 bucket name (defaults to production bucket if None)
            collection_id: Collection ID containing the bundle
            bundle_id: Bundle ID
            
        Returns:
            XML content as bytes, or None if not found
        """
        # Default to production bucket if none provided
        if bucket is None:
            bucket = self.production_bucket
            
        if not all([collection_id, bundle_id]):
            logger.error("Missing required parameters for bundle XML retrieval")
            return None
            
        # Form the bundle XML path
        xml_path = self.form_bundle_xml_path(collection_id, bundle_id)
        
        # Get the XML content
        return self.read_s3_object(bucket, xml_path) 
