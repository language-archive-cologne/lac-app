"""
Bucket metadata service for storage operations.

This service handles BLAM (Collection/Bundle) metadata enrichment and OCFL
detection. It provides stateless utilities that can be imported by listing
services or views to add metadata to folder listings.
"""
import logging
from typing import Dict, List, Any, Set

from .service_context import StorageServiceContext
from .collection_service import CollectionService
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

logger = logging.getLogger(__name__)


class BucketMetadataService:
    """
    Service for enriching bucket listings with BLAM metadata.

    Handles bulk lookups of Collections and Bundles by directory name
    and provides efficient metadata tagging for folder items.
    """

    def __init__(
        self, context: StorageServiceContext, collection_service: CollectionService
    ):
        """
        Initialize the metadata service.

        Args:
            context: Shared service context
            collection_service: Collection service for path validation
        """
        self.context = context
        self.collection_service = collection_service

    def build_blam_metadata_index(
        self,
        bucket_name: str,
        folder_items: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build a lookup of BLAM metadata for a collection of folder entries.

        Args:
            bucket_name: The bucket being inspected
            folder_items: Folder entries returned from S3

        Returns:
            Mapping of folder path -> BLAM metadata dict with keys:
                - is_blam_object (bool)
                - blam_type (str): "collection" or "bundle"
                - blam_id (str): Database primary key
        """
        # Only process production bucket
        if bucket_name != self.context.production_bucket or not folder_items:
            return {}

        collection_dir_names: Set[str] = set()
        collection_paths: Dict[str, str] = {}
        bundle_dir_names: Set[str] = set()

        # First pass: identify potential BLAM objects by path structure
        for item in folder_items:
            path = item.get("path")
            if not path:
                continue

            normalized_path = path.rstrip("/")
            if not normalized_path:
                continue

            try:
                # Check if this looks like a collection path
                if self.collection_service.is_collection_path(path):
                    candidate_name = normalized_path.split("/")[-1]
                    if candidate_name:
                        collection_dir_names.add(candidate_name)
                        collection_paths[path] = candidate_name
            except Exception as exc:
                logger.debug("Failed to evaluate collection path %s: %s", path, exc)

            # Any nested folder could be a bundle
            parts = normalized_path.split("/")
            if len(parts) >= 2 and parts[-1]:
                bundle_dir_names.add(parts[-1])

        metadata: Dict[str, Dict[str, Any]] = {}
        if not collection_dir_names and not bundle_dir_names:
            return metadata

        # Bulk load collection metadata
        collections_by_name: Dict[str, str] = {}
        if collection_dir_names:
            try:
                collection_rows = Collection.objects.filter(
                    general_info__directory_name__in=collection_dir_names
                ).values_list("general_info__directory_name", "pk")
                collections_by_name = {
                    dir_name: str(pk) for dir_name, pk in collection_rows if dir_name
                }
            except Exception as exc:
                logger.warning("Failed to bulk load collection metadata: %s", exc)

        # Bulk load bundle metadata (excluding names that matched collections)
        bundle_lookup_names = {
            name
            for name in bundle_dir_names
            if name and name not in collections_by_name
        }
        bundles_by_name: Dict[str, str] = {}
        if bundle_lookup_names:
            try:
                bundle_rows = Bundle.objects.filter(
                    general_info__directory_name__in=bundle_lookup_names
                ).values_list("general_info__directory_name", "pk")
                bundles_by_name = {
                    dir_name: str(pk) for dir_name, pk in bundle_rows if dir_name
                }
            except Exception as exc:
                logger.warning("Failed to bulk load bundle metadata: %s", exc)

        # Second pass: build metadata index
        for item in folder_items:
            path = item.get("path")
            if not path:
                continue

            normalized_path = path.rstrip("/")
            if not normalized_path:
                continue

            dir_name = normalized_path.split("/")[-1]
            if not dir_name:
                continue

            # Check if this is a collection
            collection_name = collection_paths.get(path)
            if collection_name:
                collection_id = collections_by_name.get(collection_name)
                if collection_id:
                    metadata[path] = {
                        "is_blam_object": True,
                        "blam_type": "collection",
                        "blam_id": collection_id,
                    }
                    continue

            # Check if this is a bundle
            parts = normalized_path.split("/")
            if len(parts) >= 2:
                bundle_id = bundles_by_name.get(dir_name)
                if bundle_id:
                    metadata[path] = {
                        "is_blam_object": True,
                        "blam_type": "bundle",
                        "blam_id": bundle_id,
                    }

        return metadata

    def is_blam_object(self, bucket_name: str, path: str) -> Dict[str, Any]:
        """
        Check if a single path corresponds to a BLAM model (Collection or Bundle).

        Args:
            bucket_name: The bucket name
            path: The path to check

        Returns:
            Dict with keys:
                - is_blam_object (bool): Whether this is a BLAM object
                - blam_type (str, optional): "collection" or "bundle"
                - blam_id (str, optional): Database ID
        """
        result = {"is_blam_object": False, "blam_type": None, "blam_id": None}

        # Only check production bucket
        if bucket_name != self.context.production_bucket:
            return result

        try:
            # Check for collection
            if self.collection_service.is_collection_path(path):
                collection_name = path.rstrip("/").split("/")[-1]

                try:
                    collection = Collection.objects.filter(
                        general_info__directory_name=collection_name
                    ).first()

                    if collection:
                        result["is_blam_object"] = True
                        result["blam_type"] = "collection"
                        result["blam_id"] = str(collection.pk)
                        logger.info(
                            f"Identified path {path} as Collection with ID {collection.pk}"
                        )
                        return result
                except Exception as e:
                    logger.error(
                        f"Error querying Collection for path {path}: {str(e)}"
                    )

            # Check for bundle
            parts = path.rstrip("/").split("/")
            if len(parts) >= 2:
                bundle_name = parts[-1]

                try:
                    bundle = Bundle.objects.filter(
                        general_info__directory_name=bundle_name
                    ).first()

                    if bundle:
                        result["is_blam_object"] = True
                        result["blam_type"] = "bundle"
                        result["blam_id"] = str(bundle.pk)
                        logger.info(
                            f"Identified path {path} as Bundle with ID {bundle.pk}"
                        )
                        return result
                except Exception as e:
                    logger.error(f"Error querying Bundle for path {path}: {str(e)}")

        except Exception as e:
            logger.error(f"Error in is_blam_object for path {path}: {str(e)}")

        return result

    def enrich_folder_items(
        self,
        bucket_name: str,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Enrich a list of folder items with BLAM metadata.

        Args:
            bucket_name: The bucket name
            items: List of folder/file items from S3 listing

        Returns:
            List of enriched items with BLAM metadata added to folders
        """
        # Extract folder items for bulk metadata lookup
        folder_items = [entry for entry in items if entry.get("is_dir")]
        blam_metadata = self.build_blam_metadata_index(bucket_name, folder_items)

        # Enrich items with BLAM metadata
        enriched_items = []
        for item in items:
            enriched_item = item.copy()

            if item.get("is_dir"):
                blam_info = blam_metadata.get(item.get("path"))
                if blam_info:
                    enriched_item.update(blam_info)

            enriched_items.append(enriched_item)

        return enriched_items
