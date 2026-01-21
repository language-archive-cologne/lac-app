from django.core.management.base import BaseCommand

from lacos.storage.models import S3FileObject
from lacos.storage.services.upload_audit_repair_service import UploadAuditRepairService


class Command(BaseCommand):
    help = "Repair S3FileObject.s3_key values using upload metadata and S3 lookups."

    def add_arguments(self, parser):
        parser.add_argument("--session", type=str, help="UploadSession UUID to scope updates.")
        parser.add_argument("--bucket", type=str, help="Override bucket name for lookups.")
        parser.add_argument("--limit", type=int, default=0, help="Limit rows processed.")
        parser.add_argument("--dry-run", action="store_true", help="Print changes without updating.")

    def handle(self, *args, **options):
        session_id = options.get("session")
        bucket_name = options.get("bucket")
        limit = options.get("limit") or 0
        dry_run = options.get("dry_run", False)

        queryset = S3FileObject.objects.select_related("session").order_by("created_at")
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if bucket_name:
            queryset = queryset.filter(session__bucket_name=bucket_name)
        if limit > 0:
            queryset = queryset[:limit]

        service = UploadAuditRepairService()

        updated = 0
        unchanged = 0
        missing = 0
        skipped = 0

        for file_obj in queryset:
            result = service.repair_file_object(
                file_obj,
                bucket_name=bucket_name,
                dry_run=dry_run,
            )
            if result.status == "updated":
                updated += 1
                self.stdout.write(
                    f"UPDATED {file_obj.id}: {file_obj.s3_key} -> {result.s3_key}"
                )
            elif result.status == "unchanged":
                unchanged += 1
            elif result.status == "missing":
                missing += 1
                self.stdout.write(
                    f"MISSING {file_obj.id}: expected {result.expected_key}"
                )
            else:
                skipped += 1
                self.stdout.write(
                    f"SKIPPED {file_obj.id}: {result.error or 'no_action'}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. updated={updated} unchanged={unchanged} missing={missing} skipped={skipped}"
            )
        )
