"""Management command to update CORS configuration on all S3 buckets."""
from django.core.management.base import BaseCommand

from lacos.storage.services import ResourceMappingService


class Command(BaseCommand):
    help = "Update CORS configuration on all S3 buckets to enable video streaming with range requests"

    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='List all available buckets without updating CORS',
        )
        parser.add_argument(
            '--bucket',
            type=str,
            help='Update CORS for a specific bucket only',
        )

    def handle(self, *args, **options):
        service = ResourceMappingService(skip_bucket_check=True)

        # List mode - just show available buckets
        if options['list']:
            self.stdout.write("Listing all available buckets...")
            try:
                response = service.s3_client.list_buckets()
                buckets = [b['Name'] for b in response.get('Buckets', [])]
                self.stdout.write(f"Found {len(buckets)} buckets:")
                for bucket in buckets:
                    self.stdout.write(f"  - {bucket}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to list buckets: {e}"))
            return

        # Single bucket mode
        if options['bucket']:
            buckets_to_update = [options['bucket']]
        else:
            # Get all available buckets from S3
            self.stdout.write("Discovering available buckets...")
            try:
                response = service.s3_client.list_buckets()
                buckets_to_update = [b['Name'] for b in response.get('Buckets', [])]
                self.stdout.write(f"Found {len(buckets_to_update)} buckets: {buckets_to_update}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to list buckets: {e}"))
                self.stdout.write("Falling back to configured workspace buckets...")
                buckets_to_update = service.workspace_buckets

        self.stdout.write("\nUpdating CORS configuration...")

        for bucket_name in buckets_to_update:
            self.stdout.write(f"\nUpdating CORS for bucket: {bucket_name}")
            result = service.ensure_cors_enabled(bucket_name)

            if result["success"]:
                if result.get("updated", False):
                    self.stdout.write(self.style.SUCCESS(f"  CORS updated for {bucket_name}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"  CORS already configured for {bucket_name}"))
            else:
                self.stdout.write(self.style.ERROR(f"  Failed to update CORS for {bucket_name}: {result.get('error')}"))

        self.stdout.write(self.style.SUCCESS("\nDone!"))
