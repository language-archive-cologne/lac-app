import logging
from typing import Dict, List, Optional
from uuid import UUID

from django.db import close_old_connections, connection
from django.core.management.base import BaseCommand

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.ingest.services.reindex_service import (
    BundleReindexResult,
    CollectionReindexResult,
    reindex_bundle_xml_status,
    reindex_collection_xml_status,
)
from lacos.storage.services.file_discovery_service import FileDiscoveryService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reindex collections and bundles from S3 XML (update existing records)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--identifier",
            type=str,
            help="Collection md_self_link identifier to reindex",
        )
        parser.add_argument(
            "--prefix",
            type=str,
            help="S3 prefix to scan for collection/bundle XML",
        )
        parser.add_argument(
            "--bucket",
            type=str,
            help="S3 bucket name (defaults to configured production bucket)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Reindex all collections found in the database",
        )
        parser.add_argument(
            "--update-bundles",
            action="store_true",
            help="Also reindex bundle XMLs associated with the collection",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be reindexed without changing data",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reparse XML even when the stored S3 ETag is unchanged",
        )

    def handle(self, *args, **options):
        identifier = options.get("identifier")
        prefix = options.get("prefix")
        update_bundles = options.get("update_bundles")
        dry_run = options.get("dry_run")
        force = bool(options.get("force"))

        discovery_service = FileDiscoveryService()
        bucket = options.get("bucket") or discovery_service.production_bucket

        if not identifier and not prefix and not options.get("all"):
            self.stdout.write(self.style.ERROR("Specify --identifier, --prefix, or --all"))
            return 1

        if identifier:
            collection = Collection.objects.filter(identifier=identifier).first()
            if not collection:
                self.stdout.write(
                    self.style.ERROR(f"Collection '{identifier}' not found")
                )
                return 1
            s3_key = collection.import_object_key
            bucket_to_use = options.get("bucket") or collection.import_bucket or bucket
            if not s3_key:
                self.stdout.write(
                    self.style.ERROR(
                        "Collection has no import_object_key; use --prefix instead."
                    )
                )
                return 1
            if not self._s3_object_exists(discovery_service, bucket_to_use, s3_key):
                self._remove_missing_collection(collection, dry_run=dry_run)
                return 0

            collection_result = self._reindex_collection(
                bucket_to_use,
                s3_key,
                dry_run=dry_run,
                force=force,
                discovery_service=discovery_service,
            )

            bundle_results = []
            if update_bundles:
                bundle_results = self._reindex_bundles_for_collection(
                    collection,
                    bucket_to_use,
                    dry_run=dry_run,
                    force=force,
                    discovery_service=discovery_service,
                )

            # Update S3 resource locations
            self._maybe_update_s3_resource_locations(
                collection_result,
                bundle_results,
                dry_run=dry_run,
            )
            return 0

        if prefix:
            candidates = discovery_service.find_collection_and_bundle_xmls_s3(
                bucket,
                prefix,
            )
            collection_keys = candidates.get("potential_collection_xmls", [])
            bundle_keys = candidates.get("potential_bundle_xmls", [])
            bundle_keys_by_collection = self._group_bundle_keys_by_collection(bundle_keys)
            if not collection_keys:
                self.stdout.write(
                    self.style.ERROR(
                        f"No collection XML found under prefix {bucket}/{prefix}"
                    )
                )
                return 1

            for collection_key in collection_keys:
                collection_result = self._reindex_collection(
                    bucket,
                    collection_key,
                    dry_run=dry_run,
                    force=force,
                    discovery_service=discovery_service,
                )
                bundle_results = []
                if update_bundles:
                    collection_identifier = self._infer_collection_identifier(collection_key)
                    scoped_bundle_keys = bundle_keys
                    if collection_identifier:
                        scoped_bundle_keys = bundle_keys_by_collection.get(
                            collection_identifier,
                            [],
                        )
                    bundle_results = self._reindex_bundle_keys(
                        bucket,
                        scoped_bundle_keys,
                        dry_run=dry_run,
                        force=force,
                        discovery_service=discovery_service,
                    )
                # Update S3 resource locations
                self._maybe_update_s3_resource_locations(
                    collection_result,
                    bundle_results,
                    dry_run=dry_run,
                )
            return 0

        if options.get("all"):
            collection_ids = list(Collection.objects.values_list("id", flat=True))
            for coll_id in collection_ids:
                close_old_connections()
                collection = Collection.objects.get(id=coll_id)
                s3_key = collection.import_object_key
                bucket_to_use = options.get("bucket") or collection.import_bucket or bucket
                if not s3_key:
                    logger.warning(
                        "Skipping collection %s: missing import_object_key",
                        collection.id,
                    )
                    continue
                if not self._s3_object_exists(discovery_service, bucket_to_use, s3_key):
                    self._remove_missing_collection(collection, dry_run=dry_run)
                    continue
                collection_result = self._reindex_collection(
                    bucket_to_use,
                    s3_key,
                    dry_run=dry_run,
                    force=force,
                    discovery_service=discovery_service,
                )
                bundle_results = []
                if update_bundles:
                    bundle_results = self._reindex_bundles_for_collection(
                        collection,
                        bucket_to_use,
                        dry_run=dry_run,
                        force=force,
                        discovery_service=discovery_service,
                    )
                # Update S3 resource locations
                self._maybe_update_s3_resource_locations(
                    collection_result,
                    bundle_results,
                    dry_run=dry_run,
                )
            connection.close()
            return 0

        return 0

    def _s3_object_exists(
        self,
        discovery_service: FileDiscoveryService,
        bucket: str,
        s3_key: str,
    ) -> bool:
        """Return False only when S3 confirms the object is missing."""
        try:
            return discovery_service.head_s3_object(bucket, s3_key) is not None
        except Exception as exc:
            logger.warning(
                "Could not verify collection XML %s/%s before reindex: %s",
                bucket,
                s3_key,
                exc,
            )
            return True

    def _remove_missing_collection(
        self,
        collection: Collection,
        *,
        dry_run: bool = False,
    ) -> None:
        """Remove a DB collection whose import XML no longer exists in S3."""
        from lacos.ingest.services.orphan_cleanup import delete_orphaned_bundles

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN: would remove missing collection {collection.identifier}"
                )
            )
            return

        collection_id = collection.id
        collection_identifier = collection.identifier
        deleted_bundles = delete_orphaned_bundles(collection_id, s3_bundle_keys=[])
        collection.delete()
        self.stdout.write(
            self.style.WARNING(
                "Removed missing collection "
                f"{collection_identifier} and {len(deleted_bundles)} linked bundle(s)"
            )
        )

    @staticmethod
    def _infer_collection_identifier(s3_key: str) -> Optional[str]:
        if not s3_key:
            return None
        parts = [part for part in s3_key.split("/") if part]
        if not parts:
            return None
        return parts[0]

    def _group_bundle_keys_by_collection(
        self,
        bundle_keys: List[str],
    ) -> Dict[str, List[str]]:
        grouped_keys: Dict[str, List[str]] = {}
        for bundle_key in bundle_keys:
            collection_identifier = self._infer_collection_identifier(bundle_key)
            if not collection_identifier:
                continue
            grouped_keys.setdefault(collection_identifier, []).append(bundle_key)
        return grouped_keys

    def _reindex_collection(
        self,
        bucket: str,
        s3_key: str,
        dry_run: bool = False,
        force: bool = False,
        discovery_service: Optional[FileDiscoveryService] = None,
    ):
        if dry_run:
            self.stdout.write(f"DRY RUN: would reindex collection {bucket}/{s3_key}")
            return None
        result = reindex_collection_xml_status(
            bucket=bucket,
            s3_key=s3_key,
            force=force,
            discovery_service=discovery_service,
        )
        if result:
            if result.skipped:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped unchanged collection {result.collection_id} from {bucket}/{s3_key}"
                    )
                )
                return result
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reindexed collection {result.collection_id} from {bucket}/{s3_key}"
                )
            )
            return result
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"Failed to reindex collection from {bucket}/{s3_key}"
                )
            )
            return None

    def _maybe_update_s3_resource_locations(
        self,
        collection_result: Optional[CollectionReindexResult],
        bundle_results: list,
        dry_run: bool = False,
    ):
        if not collection_result:
            return
        if self._has_reindexed_xml(collection_result, bundle_results):
            self._update_s3_resource_locations(
                collection_result.collection_id,
                bundle_results,
                dry_run=dry_run,
                fallback_to_all_bundles=True,
            )
            return
        if self._has_missing_s3_resource_locations(
            collection_result.collection_id,
            bundle_results,
        ):
            self._update_s3_resource_locations(
                collection_result.collection_id,
                bundle_results,
                dry_run=dry_run,
                fallback_to_all_bundles=False,
            )
            return
        self.stdout.write(
            self.style.WARNING(
                f"S3 resource locations unchanged; skipped mapping for collection {collection_result.collection_id}"
            )
        )

    def _update_s3_resource_locations(
        self,
        collection_id,
        bundle_results: list,
        dry_run: bool = False,
        fallback_to_all_bundles: bool = True,
    ):
        """Update S3ResourceLocation entries for collection and its resources."""
        if dry_run:
            self.stdout.write(f"DRY RUN: would update S3 resource locations for collection {collection_id}")
            return

        # Build list of (bundle_id, bundle_resources_id) pairs
        bundle_resources_pairs = [
            (bundle_id, bundle_resources_id)
            for bundle_id, bundle_resources_id in (
                self._bundle_result_pair(result) for result in bundle_results
            )
            if bundle_id and bundle_resources_id
        ]

        # Passing [] to map_collection_hierarchy means "map no bundles".
        # Passing None triggers fallback discovery of all bundles/resources
        # belonging to the collection, which is what we want when reindex
        # did not return explicit bundle/resource pairs.
        pairs_for_mapping = bundle_resources_pairs
        if fallback_to_all_bundles and not bundle_resources_pairs:
            pairs_for_mapping = None

        try:
            mapping_service = ResourceMappingService()
            total_mapped = mapping_service.map_collection_hierarchy(
                collection_id=collection_id,
                bundle_resources_pairs=pairs_for_mapping,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated S3 resource locations: {total_mapped} objects mapped"
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to update S3 resource locations: {e}")
            )

    def _has_reindexed_xml(
        self,
        collection_result: CollectionReindexResult,
        bundle_results: list,
    ) -> bool:
        if not collection_result.skipped:
            return True
        return any(not self._bundle_result_was_skipped(result) for result in bundle_results)

    def _has_missing_s3_resource_locations(
        self,
        collection_id: UUID,
        bundle_results: list,
    ) -> bool:
        from django.contrib.contenttypes.models import ContentType
        from lacos.blam.models.bundle.bundle_structural_info import (
            BundleAdditionalMetadataFile,
            BundleResources,
            MediaResource,
            OtherResource,
            WrittenResource,
        )
        from lacos.blam.models.collection.collection_structural_info import (
            CollectionAdditionalMetadataFile,
        )
        from lacos.storage.models.s3_resource_location import S3ResourceLocation

        models_by_class = ContentType.objects.get_for_models(
            Collection,
            Bundle,
            CollectionAdditionalMetadataFile,
            BundleAdditionalMetadataFile,
            MediaResource,
            WrittenResource,
            OtherResource,
        )
        targets = set()

        def add_target(obj) -> None:
            content_type = models_by_class[obj.__class__]
            targets.add((content_type.id, str(obj.pk)))

        collection = (
            Collection.objects
            .filter(id=collection_id)
            .prefetch_related("structural_info__additional_metadata_files")
            .first()
        )
        if not collection:
            return True
        add_target(collection)
        for structural_info in collection.structural_info.all():
            for metadata_file in structural_info.additional_metadata_files.all():
                add_target(metadata_file)

        bundle_result_pairs = [self._bundle_result_pair(result) for result in bundle_results]
        bundle_ids = [bundle_id for bundle_id, _ in bundle_result_pairs if bundle_id]
        bundle_resources_ids = [
            bundle_resources_id
            for _, bundle_resources_id in bundle_result_pairs
            if bundle_resources_id
        ]

        for bundle in (
            Bundle.objects
            .filter(id__in=bundle_ids)
            .prefetch_related("structural_info__additional_metadata_files")
        ):
            add_target(bundle)
            for structural_info in bundle.structural_info.all():
                for metadata_file in structural_info.additional_metadata_files.all():
                    add_target(metadata_file)

        bundle_resources_qs = BundleResources.objects.filter(
            id__in=bundle_resources_ids,
        ).prefetch_related(
            "bundle_media_resources",
            "bundle_written_resources",
            "bundle_other_resources",
        )
        for bundle_resources in bundle_resources_qs:
            for media_resource in bundle_resources.bundle_media_resources.all():
                add_target(media_resource)
            for written_resource in bundle_resources.bundle_written_resources.all():
                add_target(written_resource)
            for other_resource in bundle_resources.bundle_other_resources.all():
                add_target(other_resource)

        existing_targets = set(
            S3ResourceLocation.objects.filter(
                content_type_id__in=[content_type_id for content_type_id, _ in targets],
                object_id__in=[object_id for _, object_id in targets],
            ).values_list("content_type_id", "object_id")
        )
        return bool(targets - existing_targets)

    def _bundle_result_pair(self, result) -> tuple:
        if isinstance(result, BundleReindexResult):
            return result.bundle_id, result.bundle_resources_id
        return result

    def _bundle_result_was_skipped(self, result) -> bool:
        if isinstance(result, BundleReindexResult):
            return result.skipped
        return False

    def _reindex_bundles_for_collection(
        self,
        collection: Collection,
        bucket: str,
        dry_run: bool = False,
        force: bool = False,
        discovery_service: Optional[FileDiscoveryService] = None,
    ) -> list:
        """Reindex bundles for collection and return results.

        After reindexing, removes orphaned bundles whose XML no longer
        exists in S3.
        """
        service = discovery_service or FileDiscoveryService()

        # Always discover bundle keys from S3 so we have the authoritative
        # list for orphan cleanup — DB-derived keys would include orphans.
        s3_bundle_keys = []
        if collection.import_object_key:
            prefix = f"{collection.import_object_key.split('/')[0]}/"
            candidates = service.find_collection_and_bundle_xmls_s3(
                bucket,
                prefix,
            )
            s3_bundle_keys = candidates.get("potential_bundle_xmls", [])

        if not s3_bundle_keys:
            # Fallback to DB-derived keys when S3 discovery returns nothing
            bundle_qs = Bundle.objects.filter(
                structural_info__is_member_of_collection=collection
            ).distinct()
            s3_bundle_keys = [
                b.import_object_key for b in bundle_qs if b.import_object_key
            ]

        results = self._reindex_bundle_keys(
            bucket,
            s3_bundle_keys,
            dry_run=dry_run,
            force=force,
            discovery_service=service,
        )

        # Remove bundles that no longer have XML in S3
        if not dry_run:
            self._cleanup_orphan_bundles(collection, s3_bundle_keys)

        return results

    def _cleanup_orphan_bundles(
        self,
        collection: Collection,
        s3_bundle_keys: List[str],
    ) -> None:
        """Delete bundles linked to collection that have no XML in S3."""
        from lacos.ingest.services.orphan_cleanup import delete_orphaned_bundles

        deleted = delete_orphaned_bundles(collection.id, s3_bundle_keys)
        if deleted:
            self.stdout.write(
                self.style.WARNING(
                    f"Removed {len(deleted)} orphaned bundle(s) from {collection.identifier}"
                )
            )

    def _reindex_bundle_keys(
        self,
        bucket: str,
        bundle_keys: List[str],
        dry_run: bool = False,
        force: bool = False,
        discovery_service: Optional[FileDiscoveryService] = None,
    ) -> list:
        """Reindex bundles and return list of (bundle_id, bundle_resources_id) tuples."""
        results = []
        if not bundle_keys:
            self.stdout.write(self.style.WARNING("No bundle XML keys to reindex"))
            return results
        seen_bundle_keys = set()
        for bundle_key in bundle_keys:
            if not bundle_key or bundle_key in seen_bundle_keys:
                continue
            seen_bundle_keys.add(bundle_key)
            close_old_connections()
            if dry_run:
                self.stdout.write(
                    f"DRY RUN: would reindex bundle {bucket}/{bundle_key}"
                )
                continue
            result = reindex_bundle_xml_status(
                bucket=bucket,
                s3_key=bundle_key,
                force=force,
                discovery_service=discovery_service,
            )
            if result:
                results.append(result)
                if result.skipped:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped unchanged bundle {result.bundle_id} (resources {result.bundle_resources_id})"
                        )
                    )
                    continue
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Reindexed bundle {result.bundle_id} (resources {result.bundle_resources_id})"
                    )
                )
            else:
                self.stdout.write(
                self.style.ERROR(
                    f"Failed to reindex bundle from {bucket}/{bundle_key}"
                )
            )
        return results
