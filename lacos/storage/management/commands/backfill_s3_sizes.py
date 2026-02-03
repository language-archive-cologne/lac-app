"""Management command to backfill size_bytes from S3 for S3ResourceLocation records."""

import logging

from django.core.management.base import BaseCommand

from botocore.exceptions import ClientError

from lacos.storage.models.s3_resource_location import S3ResourceLocation
from lacos.storage.services.base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill size_bytes from S3 for S3ResourceLocation records with missing sizes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update all records, even those with existing size_bytes",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        # Get S3 client via BaseStorageService
        storage_service = BaseStorageService()
        s3_client = storage_service.s3_client

        # Query records to update
        if force:
            queryset = S3ResourceLocation.objects.all()
        else:
            queryset = S3ResourceLocation.objects.filter(size_bytes__isnull=True)

        total = queryset.count()
        self.stdout.write(f"Found {total} records to process")

        updated = 0
        errors = 0

        for location in queryset.iterator():
            try:
                # Get object metadata from S3
                response = s3_client.head_object(
                    Bucket=location.s3_bucket,
                    Key=location.s3_key,
                )

                size = response.get("ContentLength", 0)
                content_type = response.get("ContentType")

                if dry_run:
                    self.stdout.write(
                        f"  [DRY-RUN] Would update {location.s3_bucket}/{location.s3_key}: "
                        f"size={size}, mime={content_type}"
                    )
                else:
                    location.size_bytes = size
                    if content_type and not location.mime_type:
                        location.mime_type = content_type
                    location.save(update_fields=["size_bytes", "mime_type"])
                    self.stdout.write(
                        f"  Updated {location.s3_bucket}/{location.s3_key}: size={size}"
                    )

                updated += 1

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                self.stderr.write(
                    f"  Error for {location.s3_bucket}/{location.s3_key}: {error_code}"
                )
                errors += 1
            except Exception as e:
                self.stderr.write(
                    f"  Error for {location.s3_bucket}/{location.s3_key}: {e}"
                )
                errors += 1

        action = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{action} {updated} records, {errors} errors out of {total} total"
            )
        )
