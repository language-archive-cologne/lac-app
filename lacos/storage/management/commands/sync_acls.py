from django.core.management.base import BaseCommand, CommandError

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.services.acl_sync_service import ACLSyncResult
from lacos.storage.services.registry import get_acl_sync_service


class Command(BaseCommand):
    help = "Sync ACL metadata from OCFL storage into the ACLPermissions table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--collection-id",
            action="append",
            dest="collection_ids",
            help="Limit sync to the specified collection UUID (can be provided multiple times).",
        )
        parser.add_argument(
            "--bundle-id",
            action="append",
            dest="bundle_ids",
            help="Limit sync to the specified bundle UUID (can be provided multiple times).",
        )
        parser.add_argument(
            "--skip-collections",
            action="store_true",
            help="Skip syncing collections.",
        )
        parser.add_argument(
            "--skip-bundles",
            action="store_true",
            help="Skip syncing bundles.",
        )

    def handle(self, *args, **options):
        service = get_acl_sync_service()

        collection_ids = options.get("collection_ids") or []
        bundle_ids = options.get("bundle_ids") or []
        skip_collections = options.get("skip_collections", False)
        skip_bundles = options.get("skip_bundles", False)

        if skip_collections and skip_bundles:
            raise CommandError("Both collections and bundles are skipped; nothing to sync.")

        if collection_ids and skip_collections:
            raise CommandError("Cannot specify --collection-id when --skip-collections is set.")

        if bundle_ids and skip_bundles:
            raise CommandError("Cannot specify --bundle-id when --skip-bundles is set.")

        results: list[ACLSyncResult] = []

        if not skip_collections:
            collections = self._resolve_collections(collection_ids)
            for collection in collections:
                result = service.sync_collection(collection)
                self._emit_result(result)
                results.append(result)

        if not skip_bundles:
            bundles = self._resolve_bundles(bundle_ids)
            for bundle in bundles:
                result = service.sync_bundle(bundle)
                self._emit_result(result)
                results.append(result)

        if not results:
            self.stdout.write(self.style.WARNING("No ACL records processed."))
            return

        updated = sum(1 for r in results if r.updated)
        missing = sum(1 for r in results if not r.found)
        errors = [r for r in results if r.error]

        summary = f"ACL sync complete: total={len(results)} updated={updated} missing={missing}"
        if errors:
            summary += f" errors={len(errors)}"
        self.stdout.write(self.style.SUCCESS(summary))

        for result in errors:
            self.stdout.write(
                self.style.ERROR(
                    f"  Error for {result.object_type} {result.object_id}: {result.error}"
                )
            )

    def _emit_result(self, result: ACLSyncResult) -> None:
        prefix = f"{result.bucket}/{result.key}" if result.bucket and result.key else "unknown location"
        if result.error:
            self.stdout.write(
                self.style.ERROR(
                    f"[ERROR] {result.object_type} {result.object_id}: {result.error} ({prefix})"
                )
            )
        elif not result.found:
            self.stdout.write(
                self.style.WARNING(
                    f"[MISSING] {result.object_type} {result.object_id}: ACL file not found ({prefix})"
                )
            )
        elif result.updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[UPDATED] {result.object_type} {result.object_id}: synced from {prefix}"
                )
            )
        else:
            self.stdout.write(
                f"[UNCHANGED] {result.object_type} {result.object_id}: already up to date ({prefix})"
            )

    @staticmethod
    def _resolve_collections(collection_ids: list[str]) -> list[Collection]:
        if not collection_ids:
            return list(Collection.objects.all())

        found = list(Collection.objects.filter(pk__in=collection_ids))
        missing = set(collection_ids) - {str(obj.pk) for obj in found}
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise CommandError(f"Collection(s) not found: {missing_str}")
        return found

    @staticmethod
    def _resolve_bundles(bundle_ids: list[str]) -> list[Bundle]:
        queryset = Bundle.objects.prefetch_related("structural_info__is_member_of_collection")
        if not bundle_ids:
            return list(queryset.all())

        found = list(queryset.filter(pk__in=bundle_ids))
        missing = set(bundle_ids) - {str(obj.pk) for obj in found}
        if missing:
            missing_str = ", ".join(sorted(missing))
            raise CommandError(f"Bundle(s) not found: {missing_str}")
        return found
