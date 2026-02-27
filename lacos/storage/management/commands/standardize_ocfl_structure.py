import shutil
import boto3
from pathlib import Path
from datetime import datetime
from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand
from django.conf import settings
from urllib.parse import urlparse
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.ocfl_service import OCFLService
import logging

logger = logging.getLogger(__name__)

def is_collection(directory):
    """
    Determine if a directory is a collection by checking if its name matches
    its parent directory name.
    
    For example:
    - /data/algerien/algerien -> This is a collection
    - /data/algerien/alwateti_nonstructured_1 -> This is a bundle
    """
    if isinstance(directory, str):
        parts = directory.rstrip('/').split('/')
        return len(parts) >= 2 and parts[-1] == parts[-2]
    else:
        directory_path = Path(directory)
        parent_dir = directory_path.parent
        return directory_path.name == parent_dir.name


class PathHandler:
    """Handle both S3 and local paths"""
    
    def __init__(self, path_str):
        # Convert Path objects to strings
        if hasattr(path_str, 'is_dir'):  # It's a Path object
            self.original_path = str(path_str)
            self.is_s3 = False
            self.path = path_str
        else:
            self.original_path = path_str
            self.is_s3 = isinstance(path_str, str) and path_str.startswith('s3://')
            
            if self.is_s3:
                parsed = urlparse(path_str)
                self.bucket_name = parsed.netloc
                self.key = parsed.path.lstrip('/')
                self.s3_client = boto3.client('s3')
                self.s3_prefix = f"s3://{self.bucket_name}"
            else:
                self.path = Path(path_str)
    
    def exists(self):
        """Check if path exists"""
        if self.is_s3:
            try:
                if self.key.endswith('/'):
                    # For directories, check if there are any objects with this prefix
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.bucket_name,
                        Prefix=self.key,
                        MaxKeys=1
                    )
                    return 'Contents' in response
                else:
                    # For files, use head_object
                    self.s3_client.head_object(Bucket=self.bucket_name, Key=self.key)
                return True
            except ClientError:
                return False
        return self.path.exists()
    
    def is_dir(self):
        """Check if path is a directory"""
        if self.is_s3:
            try:
                # For S3, check if the path with a trailing slash exists
                # or if there are objects with this prefix
                key_with_slash = self.key.rstrip('/') + '/'
                
                # First check if the directory marker exists
                try:
                    self.s3_client.head_object(
                        Bucket=self.bucket_name,
                        Key=key_with_slash
                    )
                    return True
                except Exception:
                    # If directory marker doesn't exist, check if there are objects with this prefix
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.bucket_name,
                        Prefix=key_with_slash,
                        MaxKeys=1
                    )
                    return 'Contents' in response and len(response.get('Contents', [])) > 0
            except Exception:
                return False
        return self.path.is_dir()
    
    def glob(self, pattern):
        """Glob pattern matching"""
        if self.is_s3:
            prefix = self.key.rstrip('/') + '/'
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            # Filter objects based on pattern
            import fnmatch
            return [f"{self.s3_prefix}/{obj['Key']}" for obj in response.get('Contents', [])
                   if fnmatch.fnmatch(obj['Key'].split('/')[-1], pattern)]
        return [str(p) for p in self.path.glob(pattern)]
    
    def mkdir(self, parents=False, exist_ok=False):
        """Create directory"""
        if self.is_s3:
            # S3 doesn't need explicit directory creation
            pass
        else:
            self.path.mkdir(parents=parents, exist_ok=exist_ok)
    
    def copy_to(self, dest, recursive=False):
        """Copy to destination"""
        dest_handler = PathHandler(dest)
        
        if self.is_s3 and dest_handler.is_s3:
            # S3 to S3 copy
            if recursive:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=self.key
                )
                for obj in response.get('Contents', []):
                    source_key = obj['Key']
                    dest_key = dest_handler.key + source_key[len(self.key):]
                    if source_key != dest_key or self.bucket_name != dest_handler.bucket_name:
                        self.s3_client.copy_object(
                            CopySource={'Bucket': self.bucket_name, 'Key': source_key},
                            Bucket=dest_handler.bucket_name,
                            Key=dest_key
                        )
            else:
                if self.key != dest_handler.key or self.bucket_name != dest_handler.bucket_name:
                    self.s3_client.copy_object(
                        CopySource={'Bucket': self.bucket_name, 'Key': self.key},
                        Bucket=dest_handler.bucket_name,
                        Key=dest_handler.key
                    )
        elif self.is_s3:
            # S3 to local
            if recursive:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=self.key
                )
                for obj in response.get('Contents', []):
                    source_key = obj['Key']
                    dest_path = dest_handler.path / source_key[len(self.key):]
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    self.s3_client.download_file(
                        self.bucket_name,
                        source_key,
                        str(dest_path)
                    )
            else:
                self.s3_client.download_file(
                    self.bucket_name,
                    self.key,
                    str(dest_handler.path)
                )
        elif dest_handler.is_s3:
            # Local to S3
            if recursive:
                for source_path in self.path.rglob('*'):
                    if source_path.is_file():
                        relative_path = source_path.relative_to(self.path)
                        dest_key = f"{dest_handler.key}/{relative_path}"
                        dest_handler.s3_client.upload_file(
                            str(source_path),
                            dest_handler.bucket_name,
                            dest_key
                        )
            else:
                dest_handler.s3_client.upload_file(
                    str(self.path),
                    dest_handler.bucket_name,
                    dest_handler.key
                )
        else:
            # Local to local
            if recursive:
                shutil.copytree(str(self.path), str(dest_handler.path), dirs_exist_ok=True)
            else:
                shutil.copy2(str(self.path), str(dest_handler.path))
    
    def move(self, dest):
        """Move to destination"""
        dest_handler = PathHandler(dest)
        if str(self) != str(dest_handler):  # Only move if source and destination are different
            self.copy_to(dest)
            self.remove()
    
    def remove(self):
        """Remove path"""
        if self.is_s3:
            try:
                if self.is_dir():
                    # Delete all objects under this prefix
                    response = self.s3_client.list_objects_v2(
                        Bucket=self.bucket_name,
                        Prefix=self.key
                    )
                    for obj in response.get('Contents', []):
                        self.s3_client.delete_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                else:
                    self.s3_client.delete_object(
                        Bucket=self.bucket_name,
                        Key=self.key
                    )
            except ClientError:
                pass  # Ignore errors if object doesn't exist
        else:
            if self.path.is_dir():
                shutil.rmtree(self.path)
            else:
                self.path.unlink()
    
    def __str__(self):
        if self.is_s3:
            return f"{self.s3_prefix}/{self.key}"
        return str(self.path)


class Command(BaseCommand):
    help = 'Standardize OCFL structure for a folder in the ingest bucket'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bucket_service = BucketService()
        self.ocfl_service = OCFLService(self.bucket_service)

    def add_arguments(self, parser):
        parser.add_argument('source_prefix', type=str, help='The path in the ingest bucket to process')
        parser.add_argument('--validate-only', action='store_true', help='Only validate the structure without transforming')
        parser.add_argument('--transform-only', action='store_true', help='Only transform the structure without validating')

    def handle(self, *args, **options):
        source_prefix = options['source_prefix']
        validate_only = options.get('validate_only', False)
        transform_only = options.get('transform_only', False)

        try:
            if validate_only:
                # Only validate the structure
                result = self.ocfl_service.validate_structure(source_prefix)
                if result['success']:
                    self.stdout.write(self.style.SUCCESS('Valid OCFL structure found'))
                else:
                    self.stdout.write(self.style.WARNING(f"Invalid OCFL structure: {result['error']}"))
                    if result.get('needs_transform', False):
                        self.stdout.write(self.style.WARNING('Structure needs transformation'))

            elif transform_only:
                # Only transform the structure
                result = self.ocfl_service.transform_structure(source_prefix)
                if result['success']:
                    self.stdout.write(self.style.SUCCESS('Successfully transformed structure'))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to transform structure: {result['error']}"))

            else:
                # Full move to production process
                result = self.ocfl_service.move_to_production(source_prefix)
                if result['success']:
                    self.stdout.write(self.style.SUCCESS(result['message']))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to move to production: {result['error']}"))

        except Exception as e:
            logger.error("Error in standardize_ocfl_structure command", extra={"error": str(e)})
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
