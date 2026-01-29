import logging

from django.core.management.base import BaseCommand

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.ingest.services.reindex_service import (
    reindex_bundle_xml,
    reindex_collection_xml,
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

    def handle(self, *args, **options):
        identifier = options.get("identifier")
        prefix = options.get("prefix")
        update_bundles = options.get("update_bundles")
        dry_run = options.get("dry_run")

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

            collection_id = self._reindex_collection(
                bucket_to_use,
                s3_key,
                dry_run=dry_run,
            )

            bundle_results = []
            if update_bundles:
                bundle_results = self._reindex_bundles_for_collection(
                    collection,
                    bucket_to_use,
                    dry_run=dry_run,
                )

            # Update S3 resource locations
            if collection_id:
                self._update_s3_resource_locations(collection_id, bundle_results, dry_run=dry_run)
            return 0

        if prefix:
            candidates = discovery_service.find_collection_and_bundle_xmls_s3(
                bucket,
                prefix,
            )
            collection_keys = candidates.get("potential_collection_xmls", [])
            bundle_keys = candidates.get("potential_bundle_xmls", [])
            if not collection_keys:
                self.stdout.write(
                    self.style.ERROR(
                        f"No collection XML found under prefix {bucket}/{prefix}"
                    )
                )
                return 1

            for collection_key in collection_keys:
                collection_id = self._reindex_collection(bucket, collection_key, dry_run=dry_run)
                bundle_results = []
                if update_bundles:
                    bundle_results = self._reindex_bundle_keys(bucket, bundle_keys, dry_run=dry_run)
                # Update S3 resource locations
                if collection_id:
                    self._update_s3_resource_locations(collection_id, bundle_results, dry_run=dry_run)
            return 0

        if options.get("all"):
            collections = Collection.objects.all()
            for collection in collections:
                s3_key = collection.import_object_key
                bucket_to_use = options.get("bucket") or collection.import_bucket or bucket
                if not s3_key:
                    logger.warning(
                        "Skipping collection %s: missing import_object_key",
                        collection.id,
                    )
                    continue
                collection_id = self._reindex_collection(
                    bucket_to_use,
                    s3_key,
                    dry_run=dry_run,
                )
                bundle_results = []
                if update_bundles:
                    bundle_results = self._reindex_bundles_for_collection(
                        collection,
                        bucket_to_use,
                        dry_run=dry_run,
                    )
                # Update S3 resource locations
                if collection_id:
                    self._update_s3_resource_locations(collection_id, bundle_results, dry_run=dry_run)
            return 0

        return 0

    def _reindex_collection(self, bucket: str, s3_key: str, dry_run: bool = False):
        if dry_run:
            self.stdout.write(f"DRY RUN: would reindex collection {bucket}/{s3_key}")
            return None
        collection_id = reindex_collection_xml(bucket=bucket, s3_key=s3_key)
        if collection_id:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reindexed collection {collection_id} from {bucket}/{s3_key}"
                )
            )
            return collection_id
        else:
            self.stdout.write(
                self.style.ERROR(
                    f"Failed to reindex collection from {bucket}/{s3_key}"
                )
            )
            return None

    def _update_s3_resource_locations(self, collection_id, bundle_results: list, dry_run: bool = False):
        """Update S3ResourceLocation entries for collection and its resources."""
        if dry_run:
            self.stdout.write(f"DRY RUN: would update S3 resource locations for collection {collection_id}")
            return

        # Build list of (bundle_id, bundle_resources_id) pairs
        bundle_resources_pairs = [
            (bundle_id, bundle_resources_id)
            for bundle_id, bundle_resources_id in bundle_results
            if bundle_id and bundle_resources_id
        ]

        try:
            mapping_service = ResourceMappingService()
            total_mapped = mapping_service.map_collection_hierarchy(
                collection_id=collection_id,
                bundle_resources_pairs=bundle_resources_pairs,
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

    def _reindex_bundles_for_collection(
        self, collection: Collection, bucket: str, dry_run: bool = False
    ) -> list:
        """Reindex bundles for collection and return results."""
        bundle_qs = Bundle.objects.filter(
            structural_info__is_member_of_collection=collection
        ).distinct()
        bundle_keys = [
            bundle.import_object_key
            for bundle in bundle_qs
            if bundle.import_object_key
        ]
        if not bundle_keys and collection.import_object_key:
            prefix = f"{collection.import_object_key.split('/')[0]}/"
            candidates = FileDiscoveryService().find_collection_and_bundle_xmls_s3(
                bucket,
                prefix,
            )
            bundle_keys = candidates.get("potential_bundle_xmls", [])

        return self._reindex_bundle_keys(bucket, bundle_keys, dry_run=dry_run)

    def _reindex_bundle_keys(
        self, bucket: str, bundle_keys: list[str], dry_run: bool = False
    ) -> list:
        """Reindex bundles and return list of (bundle_id, bundle_resources_id) tuples."""
        results = []
        if not bundle_keys:
            self.stdout.write(self.style.WARNING("No bundle XML keys to reindex"))
            return results
        for bundle_key in bundle_keys:
            if dry_run:
                self.stdout.write(
                    f"DRY RUN: would reindex bundle {bucket}/{bundle_key}"
                )
                continue
            result = reindex_bundle_xml(bucket=bucket, s3_key=bundle_key)
            if result:
                bundle_id, bundle_resources_id = result
                results.append((bundle_id, bundle_resources_id))
                self.stdout.write(
                    self.style.SUCCESS(
                        "Reindexed bundle {bundle_id} (resources {bundle_resources_id})"
                    ).format(
                        bundle_id=bundle_id,
                        bundle_resources_id=bundle_resources_id,
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to reindex bundle from {bucket}/{bundle_key}"
                    )
                )
        return results
