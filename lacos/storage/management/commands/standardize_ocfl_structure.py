import os
import shutil
import json
import boto3
from pathlib import Path
from datetime import datetime
from botocore.exceptions import ClientError
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urllib.parse import urlparse


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
    help = 'Standardize OCFL directory structure for collections and bundles'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Path to process in ingest bucket')
        parser.add_argument('--dry-run', action='store_true', 
                          help='Show what would be done without making changes')
        parser.add_argument('--ingest-bucket', type=str,
                          help='Path to ingest bucket (local path or s3:// URL)')
        parser.add_argument('--production-bucket', type=str,
                          help='Path to production bucket (local path or s3:// URL)')
        parser.add_argument('--force', action='store_true', 
                          help='Force operation even if validation fails')

    def validate_structure(self, directory):
        """Validate the basic OCFL structure of a directory"""
        try:
            path_handler = PathHandler(directory)
            if not path_handler.is_dir():
                return False, "Not a directory"
            
            # Check OCFL version marker
            if not any(path_handler.glob("0=ocfl_object_*")):
                return False, "No OCFL version marker found"
            
            # Check v1/content structure
            content_path = f"{directory.rstrip('/')}/v1/content"
            content_handler = PathHandler(content_path)
            if not content_handler.is_dir():
                return False, "No v1/content directory found"
            
            # Check for XML file
            if not any(content_handler.glob("*.xml")):
                return False, "No XML file found in content directory"
            
            return True, "Valid OCFL structure"
        except Exception as e:
            return False, str(e)

    def copy_to_production(self, source_path, production_bucket, dry_run=False):
        """Copy directory from ingest to production bucket"""
        try:
            source_handler = PathHandler(source_path)
            relative_path = source_path.split('/')[-2]  # e.g., 'algerien'
            target_path = f"{production_bucket.rstrip('/')}/{relative_path}/{source_path.split('/')[-1]}"
            
            if dry_run:
                self.stdout.write(f"Would copy {source_path} to {target_path}")
                return True, target_path
            
            # Create parent directory (if needed for local paths)
            target_handler = PathHandler(target_path)
            if not target_handler.is_s3:
                target_handler.path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the directory
            source_handler.copy_to(target_path, recursive=True)
            self.stdout.write(f"Copied {source_path} to {target_path}")
            
            return True, target_path
        except Exception as e:
            return False, str(e)

    def transform_structure(self, path, dry_run=False):
        """Transform the structure with added safety checks"""
        try:
            path_handler = PathHandler(path)
            path_str = str(path_handler)
            dir_name = path_str.rstrip('/').split('/')[-1]
            
            # Create content path
            content_path = f"{path_str.rstrip('/')}/v1/content"
            content_handler = PathHandler(content_path)
            
            # Determine if it's a collection
            is_collection_dir = is_collection(path_str)
            
            if dry_run:
                self.stdout.write(f"Would process {'collection' if is_collection_dir else 'bundle'}: {dir_name}")
                return True
            
            # Create metadata directory
            metadata_path = f"{content_path}/metadata"
            metadata_handler = PathHandler(metadata_path)
            metadata_handler.mkdir(parents=True, exist_ok=True)
            self.stdout.write(f"Created metadata directory: {metadata_path}")
            
            # Move XML files to metadata
            xml_files = list(content_handler.glob('*.xml'))  # Convert to list to avoid iterator invalidation
            for xml_file in xml_files:
                if dry_run:
                    self.stdout.write(f"Would move {xml_file} to metadata directory")
                else:
                    xml_handler = PathHandler(xml_file)
                    new_path = f"{metadata_path}/{xml_file.split('/')[-1]}"
                    if new_path != xml_file:  # Only move if source and destination are different
                        xml_handler.move(new_path)
                        self.stdout.write(f"Moved {xml_file} to metadata directory")
            
            # Move acl.json to metadata if it exists
            acl_path = f"{path_str.rstrip('/')}/acl.json"
            acl_handler = PathHandler(acl_path)
            if acl_handler.exists():
                if dry_run:
                    self.stdout.write(f"Would move acl.json to metadata directory")
                else:
                    new_acl_path = f"{metadata_path}/acl.json"
                    if new_acl_path != acl_path:  # Only move if source and destination are different
                        acl_handler.move(new_acl_path)
                        self.stdout.write(f"Moved acl.json to metadata directory")
            
            # Handle Resources directory for bundles
            if not is_collection_dir:
                resources_path = f"{content_path}/Resources"
                resources_handler = PathHandler(resources_path)
                
                # For S3, we need to check if Resources directory exists by listing objects
                resources_exists = False
                if resources_handler.is_s3:
                    try:
                        response = resources_handler.s3_client.list_objects_v2(
                            Bucket=resources_handler.bucket_name,
                            Prefix=resources_handler.key.rstrip('/') + '/'
                        )
                        resources_exists = 'Contents' in response and len(response.get('Contents', [])) > 0
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"Error checking Resources directory: {str(e)}"))
                else:
                    resources_exists = resources_handler.exists()
                
                # Check if Resources directory exists
                if resources_exists:
                    data_path = f"{content_path}/data"
                    data_handler = PathHandler(data_path)
                    
                    if data_handler.exists():
                        self.stdout.write(self.style.WARNING(f"Warning: {data_path} already exists"))
                    else:
                        if dry_run:
                            self.stdout.write(f"Would rename Resources directory to data")
                        else:
                            # Create data directory
                            data_handler.mkdir(parents=True, exist_ok=True)
                            
                            # For S3, we need special handling
                            if resources_handler.is_s3:
                                # Create a directory marker for S3
                                if data_handler.is_s3:
                                    # Ensure we create a proper directory marker
                                    data_handler.s3_client.put_object(
                                        Bucket=data_handler.bucket_name,
                                        Key=data_handler.key.rstrip('/') + '/',
                                        Body=''
                                    )
                                    self.stdout.write(f"Created data directory: {data_path}")
                                
                                # List all objects under Resources prefix
                                response = resources_handler.s3_client.list_objects_v2(
                                    Bucket=resources_handler.bucket_name,
                                    Prefix=resources_handler.key.rstrip('/') + '/'
                                )
                                
                                # Move each object to the data directory
                                for obj in response.get('Contents', []):
                                    source_key = obj['Key']
                                    # Skip if this is just the directory marker
                                    if source_key.endswith('/'):
                                        continue
                                        
                                    # Get the filename from the key
                                    filename = source_key.split('/')[-1]
                                    # Create the new path in the data directory
                                    new_key = f"{data_handler.key.rstrip('/')}/{filename}"
                                    
                                    # Copy the object to the new location
                                    data_handler.s3_client.copy_object(
                                        Bucket=data_handler.bucket_name,
                                        CopySource={'Bucket': resources_handler.bucket_name, 'Key': source_key},
                                        Key=new_key
                                    )
                                    
                                    # Delete the original object
                                    resources_handler.s3_client.delete_object(
                                        Bucket=resources_handler.bucket_name,
                                        Key=source_key
                                    )
                                
                                # Delete the Resources directory marker if it exists
                                try:
                                    resources_handler.s3_client.delete_object(
                                        Bucket=resources_handler.bucket_name,
                                        Key=resources_handler.key.rstrip('/') + '/'
                                    )
                                except:
                                    pass
                                
                                self.stdout.write(f"Renamed Resources directory to data")
                            else:
                                # For local files, use the original approach
                                resource_files = list(resources_handler.glob('*'))
                                for resource in resource_files:
                                    resource_handler = PathHandler(resource)
                                    new_path = f"{data_path}/{resource.split('/')[-1]}"
                                    if new_path != resource:  # Only move if source and destination are different
                                        resource_handler.move(new_path)
                                resources_handler.remove()  # Remove empty Resources directory
                                self.stdout.write(f"Renamed Resources directory to data")
            
            return True
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error transforming directory {path}: {str(e)}"))
            return False

    def handle(self, *args, **options):
        path = options['path']
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        # Get bucket paths from options or settings
        ingest_bucket = options.get('ingest_bucket') or getattr(settings, 'INGEST_BUCKET', None)
        production_bucket = options.get('production_bucket') or getattr(settings, 'PRODUCTION_BUCKET', None)
        
        if not ingest_bucket or not production_bucket:
            raise CommandError("Ingest and production bucket paths must be specified either in settings or command line")

        try:
            # Resolve full path in ingest bucket
            ingest_path = Path(ingest_bucket) / path
            if not ingest_path.exists():
                raise CommandError(f"Path {ingest_path} not found in ingest bucket")
            
            # Validate structure
            is_valid, message = self.validate_structure(ingest_path)
            if not is_valid and not force:
                raise CommandError(f"Invalid directory structure: {message}. Use --force to override.")

            # Copy to production bucket
            copy_success, production_path = self.copy_to_production(ingest_path, production_bucket, dry_run)
            if not copy_success:
                raise CommandError(f"Failed to copy to production bucket: {production_path}")

            if not dry_run:
                # Verify the copy
                is_valid, message = self.validate_structure(production_path)
                if not is_valid:
                    # Clean up failed copy and raise error
                    shutil.rmtree(production_path)
                    raise CommandError(f"Copied directory failed validation: {message}")

            # Transform the structure in production
            if self.transform_structure(production_path, dry_run):
                if dry_run:
                    self.stdout.write(self.style.SUCCESS("Dry run completed successfully"))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f"Successfully copied to production and transformed: {production_path}"))
            else:
                if not dry_run:
                    # Clean up failed transformation
                    shutil.rmtree(production_path)
                raise CommandError("Transformation failed")

        except Exception as e:
            raise CommandError(str(e))
