"""Management command to update CORS configuration on all S3 buckets."""
from django.core.management.base import BaseCommand

from lacos.storage.services import ResourceMappingService


class Command(BaseCommand):
    help = "Update CORS configuration on all S3 buckets to enable video streaming with range requests"

    def handle(self, *args, **options):
        self.stdout.write("Updating CORS configuration on all buckets...")

        service = ResourceMappingService(skip_bucket_check=True)

        # Get all workspace buckets
        buckets = service.workspace_buckets
        self.stdout.write(f"Found {len(buckets)} workspace buckets: {buckets}")

        for bucket_name in buckets:
            self.stdout.write(f"\nUpdating CORS for bucket: {bucket_name}")
            result = service.ensure_cors_enabled(bucket_name)

            if result["success"]:
                if result.get("updated", False):
                    self.stdout.write(self.style.SUCCESS(f"  CORS updated for {bucket_name}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"  CORS already configured for {bucket_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  Failed to update CORS for {bucket_name}: {result.get('error')}"))

        # Also update production bucket if it exists
        if service.production_bucket:
            self.stdout.write(f"\nUpdating CORS for production bucket: {service.production_bucket}")
            result = service.ensure_cors_enabled(service.production_bucket)
            if result["success"]:
                if result.get("updated", False):
                    self.stdout.write(self.style.SUCCESS(f"  CORS updated for {service.production_bucket}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"  CORS already configured for {service.production_bucket}"))
            else:
                self.stdout.write(self.style.ERROR(f"  Failed: {result.get('error')}"))

        self.stdout.write(self.style.SUCCESS("\nDone!"))
