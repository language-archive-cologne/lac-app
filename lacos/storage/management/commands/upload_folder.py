import logging
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from lacos.storage.services.registry import get_bucket_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Upload a folder to the S3/MinIO bucket"

    def add_arguments(self, parser):
        parser.add_argument(
            "--folder", 
            required=True, 
            help="Path to the folder to upload"
        )
        parser.add_argument(
            "--bucket", 
            help="Name of the bucket to upload to (defaults to ingest bucket)"
        )
        parser.add_argument(
            "--prefix", 
            default="", 
            help="Prefix (path) in the bucket to upload to"
        )

    def handle(self, *args, **options):
        folder_path = options["folder"]
        bucket_name = options.get("bucket")
        prefix = options.get("prefix", "")

        # Validate folder path
        folder_path = Path(folder_path)
        if not folder_path.exists():
            raise CommandError(f"Folder does not exist: {folder_path}")
        
        if not folder_path.is_dir():
            raise CommandError(f"Path is not a directory: {folder_path}")
        
        self.stdout.write(self.style.SUCCESS(f"Starting upload of folder: {folder_path}"))
        
        # Create bucket service and upload folder
        bucket_service = get_bucket_service()
        result = bucket_service.upload_folder_to_bucket(
            str(folder_path), bucket_name, prefix
        )
        
        if result["success"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully uploaded {result['total_files']} files "
                    f"({result['total_size_formatted']}) to {result['target_bucket']}/{result['target_prefix']}"
                )
            )
            
            if result["failed_count"] > 0:
                self.stdout.write(
                    self.style.WARNING(f"Failed to upload {result['failed_count']} files:")
                )
                for failed in result["failed_files"]:
                    self.stdout.write(
                        self.style.WARNING(f"  {failed['local_path']}: {failed['error']}")
                    )
        else:
            raise CommandError(f"Failed to upload folder: {result.get('error', 'Unknown error')}") 
