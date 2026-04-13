"""
Bucket metadata service for storage operations.

This service handles BLAM (Collection/Bundle) metadata enrichment and OCFL
detection. It provides stateless utilities that can be imported by listing
services or views to add metadata to folder listings.
"""
import logging
from pathlib import PurePosixPath
from typing import Dict, List, Any

from django.db.models import Q

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

    @staticmethod
    def _object_root_from_import_key(import_object_key: str | None) -> str | None:
        """Resolve an OCFL object root path from an import key.

        Current imports store collection and bundle metadata keys inside either:
        - ``<root>/vN/metadata/<file>``
        - ``<root>/vN/content/<file>``
        - legacy non-OCFL paths such as ``<root>/<file>``
        """
        if not import_object_key:
            return None

        normalized = import_object_key.strip().strip("/")
        if not normalized:
            return None

        parts = PurePosixPath(normalized).parts
        for idx, part in enumerate(parts):
            if part.startswith("v") and part[1:].isdigit():
                return "/".join(parts[:idx]) or None

        if len(parts) >= 2:
            return "/".join(parts[:-1]) or None
        return parts[0]

    def _bucket_scope(self) -> Q:
        """Limit metadata lookups to the current production bucket when available."""
        production_bucket = self.context.production_bucket
        return (
            Q(import_bucket=production_bucket)
            | Q(import_bucket__isnull=True)
            | Q(import_bucket="")
        )

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

        collection_paths: Dict[str, str] = {}
        parsed_folder_items: List[Dict[str, Any]] = []

        # First pass: parse paths once and identify collection/bundle candidates
        for item in folder_items:
            if not item.get("is_dir", True):
                continue

            path = item.get("path")
            if not path:
                continue

            normalized_path = path.rstrip("/")
            if not normalized_path:
                continue

            parts = normalized_path.split("/")
            dir_name = parts[-1]
            if not dir_name:
                continue

            parsed_folder_items.append(
                {
                    "path": path,
                    "normalized_path": normalized_path,
                    "dir_name": dir_name,
                    "depth": len(parts),
                }
            )

            try:
                # Check if this looks like a collection path
                if self.collection_service.is_collection_path(path):
                    collection_paths[normalized_path] = dir_name
            except Exception as exc:
                logger.debug("Failed to evaluate collection path %s: %s", path, exc)

        metadata: Dict[str, Dict[str, Any]] = {}
        if not parsed_folder_items:
            return metadata

        # Bulk load collection metadata
        collections_by_path: Dict[str, str] = {}
        collection_candidate_paths = set(collection_paths.keys())
        if collection_candidate_paths:
            try:
                collection_query = Q()
                for path in collection_candidate_paths:
                    collection_query |= Q(import_object_key__startswith=f"{path}/")

                collection_rows = Collection.objects.filter(
                    self._bucket_scope() & collection_query
                ).values_list("import_object_key", "pk")
                collections_by_path = {
                    root_path: str(pk)
                    for import_key, pk in collection_rows
                    if (root_path := self._object_root_from_import_key(import_key))
                }
            except Exception as exc:
                logger.warning("Failed to bulk load collection metadata: %s", exc)

        # Bulk load bundle metadata
        bundles_by_path: Dict[str, str] = {}
        bundle_candidate_paths = {
            item_data["normalized_path"]
            for item_data in parsed_folder_items
            if item_data["depth"] >= 2
        }
        if bundle_candidate_paths:
            try:
                bundle_query = Q()
                for path in bundle_candidate_paths:
                    bundle_query |= Q(import_object_key__startswith=f"{path}/")

                bundle_rows = Bundle.objects.filter(
                    self._bucket_scope() & bundle_query
                ).values_list("import_object_key", "pk")
                bundles_by_path = {
                    root_path: str(pk)
                    for import_key, pk in bundle_rows
                    if (root_path := self._object_root_from_import_key(import_key))
                }
            except Exception as exc:
                logger.warning("Failed to bulk load bundle metadata: %s", exc)

        # Second pass: build metadata index
        for item_data in parsed_folder_items:
            path = item_data["path"]
            normalized_path = item_data["normalized_path"]
            dir_name = item_data["dir_name"]

            # Check if this is a collection
            collection_name = collection_paths.get(normalized_path)
            if collection_name:
                collection_id = collections_by_path.get(normalized_path)
                if collection_id:
                    metadata[path] = {
                        "is_blam_object": True,
                        "blam_type": "collection",
                        "blam_id": collection_id,
                    }
                    continue

            # Check if this is a bundle
            if item_data["depth"] >= 2:
                bundle_id = bundles_by_path.get(normalized_path)
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
            normalized_path = path.rstrip("/")
            if not normalized_path:
                return result

            # Check for collection
            if self.collection_service.is_collection_path(path):
                try:
                    collection = None
                    for candidate in Collection.objects.filter(
                        self._bucket_scope() & Q(import_object_key__startswith=f"{normalized_path}/")
                    ).only("pk", "import_object_key"):
                        if self._object_root_from_import_key(candidate.import_object_key) == normalized_path:
                            collection = candidate
                            break

                    if collection:
                        result["is_blam_object"] = True
                        result["blam_type"] = "collection"
                        result["blam_id"] = str(collection.pk)
                        logger.info(
                            "Identified path as Collection",
                            extra={"path": path, "collection_id": str(collection.pk)},
                        )
                        return result
                except Exception as e:
                    logger.error(
                        "Error querying Collection for path",
                        extra={"path": path, "error": str(e)},
                    )

            # Check for bundle
            parts = normalized_path.split("/")
            if len(parts) >= 2:
                try:
                    bundle = None
                    for candidate in Bundle.objects.filter(
                        self._bucket_scope() & Q(import_object_key__startswith=f"{normalized_path}/")
                    ).only("pk", "import_object_key"):
                        if self._object_root_from_import_key(candidate.import_object_key) == normalized_path:
                            bundle = candidate
                            break

                    if bundle:
                        result["is_blam_object"] = True
                        result["blam_type"] = "bundle"
                        result["blam_id"] = str(bundle.pk)
                        logger.info(
                            "Identified path as Bundle",
                            extra={"path": path, "bundle_id": str(bundle.pk)},
                        )
                        return result
                except Exception as e:
                    logger.error("Error querying Bundle for path", extra={"path": path, "error": str(e)})

        except Exception as e:
            logger.error("Error in is_blam_object for path", extra={"path": path, "error": str(e)})

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
