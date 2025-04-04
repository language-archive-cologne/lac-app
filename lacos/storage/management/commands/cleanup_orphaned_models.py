import uuid
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from lacos.storage.models import S3ResourceLocation
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Cleanup orphaned model records across the system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report orphaned records without deleting them',
        )
        parser.add_argument(
            '--app',
            type=str,
            help='Limit cleanup to a specific app (storage, blam, etc.)',
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Limit cleanup to a specific model (S3ResourceLocation, etc.)',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt (use with caution)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        app_filter = options.get('app')
        model_filter = options.get('model')
        skip_confirm = options.get('confirm', False)
        
        self.stdout.write(self.style.WARNING('STORAGE APP CLEANUP'))
        
        if app_filter is None or app_filter == 'storage':
            self.cleanup_s3_resource_locations(dry_run, skip_confirm)
        
        if app_filter is None or app_filter == 'blam':
            self.stdout.write(self.style.WARNING('\nBLAM APP CLEANUP'))
            # Add BLAM specific cleanup code here if needed
        
        self.stdout.write(self.style.SUCCESS('\nCleanup process completed.'))

    def cleanup_s3_resource_locations(self, dry_run=True, skip_confirm=False):
        """Cleanup orphaned S3ResourceLocation records."""
        self.stdout.write(self.style.NOTICE('Checking for orphaned S3ResourceLocation records...'))
        
        # Get content types for BLAM models
        collection_ct = ContentType.objects.get_for_model(Collection)
        bundle_ct = ContentType.objects.get_for_model(Bundle)
        
        # Find S3ResourceLocations with empty PIDs
        empty_pid_resources = S3ResourceLocation.objects.filter(
            Q(resource_pid='') | Q(resource_pid__isnull=True)
        )
        
        # Find S3ResourceLocations pointing to non-existent BLAM objects
        orphaned_collection_resources = []
        orphaned_bundle_resources = []
        
        # Filter for Collection references
        collection_resources = S3ResourceLocation.objects.filter(
            content_type=collection_ct
        )
        for resource in collection_resources:
            try:
                # Try to parse UUID
                obj_id = uuid.UUID(resource.object_id)
                # Check if Collection exists
                if not Collection.objects.filter(pk=obj_id).exists():
                    orphaned_collection_resources.append(resource)
            except (ValueError, TypeError):
                orphaned_collection_resources.append(resource)
        
        # Filter for Bundle references
        bundle_resources = S3ResourceLocation.objects.filter(
            content_type=bundle_ct
        )
        for resource in bundle_resources:
            try:
                # Try to parse UUID
                obj_id = uuid.UUID(resource.object_id)
                # Check if Bundle exists
                if not Bundle.objects.filter(pk=obj_id).exists():
                    orphaned_bundle_resources.append(resource)
            except (ValueError, TypeError):
                orphaned_bundle_resources.append(resource)
        
        # Display summary
        total_empty_pid = empty_pid_resources.count()
        total_orphaned_collection = len(orphaned_collection_resources)
        total_orphaned_bundle = len(orphaned_bundle_resources)
        total_orphaned = total_empty_pid + total_orphaned_collection + total_orphaned_bundle
        
        self.stdout.write(f"Found {total_orphaned} orphaned S3ResourceLocation records:")
        self.stdout.write(f"  - {total_empty_pid} with empty resource PIDs")
        self.stdout.write(f"  - {total_orphaned_collection} pointing to non-existent Collections")
        self.stdout.write(f"  - {total_orphaned_bundle} pointing to non-existent Bundles")
        
        if total_orphaned == 0:
            self.stdout.write(self.style.SUCCESS("No orphaned S3ResourceLocation records found."))
            return
        
        # Show details of records to be deleted
        if total_empty_pid > 0:
            self.stdout.write("\nS3ResourceLocations with empty PIDs:")
            for resource in empty_pid_resources:
                self.stdout.write(f"  - ID: {resource.id}, Bucket: {resource.s3_bucket}, Key: {resource.s3_key}")
        
        if total_orphaned_collection > 0:
            self.stdout.write("\nS3ResourceLocations pointing to non-existent Collections:")
            for resource in orphaned_collection_resources:
                self.stdout.write(f"  - ID: {resource.id}, Bucket: {resource.s3_bucket}, Key: {resource.s3_key}, Object ID: {resource.object_id}")
        
        if total_orphaned_bundle > 0:
            self.stdout.write("\nS3ResourceLocations pointing to non-existent Bundles:")
            for resource in orphaned_bundle_resources:
                self.stdout.write(f"  - ID: {resource.id}, Bucket: {resource.s3_bucket}, Key: {resource.s3_key}, Object ID: {resource.object_id}")
        
        # Exit if dry run
        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN: No records will be deleted. Run without --dry-run to perform deletion."))
            return
        
        # Confirm deletion
        if not skip_confirm:
            confirm = input(f"\nAre you sure you want to delete these {total_orphaned} records? [y/N]: ")
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING("Aborted. No records were deleted."))
                return
        
        # Perform deletion
        try:
            empty_pid_resources.delete()
            for resource in orphaned_collection_resources:
                resource.delete()
            for resource in orphaned_bundle_resources:
                resource.delete()
            
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {total_orphaned} orphaned S3ResourceLocation records."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error deleting records: {str(e)}"))

    def find_missing_blam_objects(self):
        """Find BLAM objects that are missing but have S3ResourceLocation entries."""
        # Get content types for BLAM models
        collection_ct = ContentType.objects.get_for_model(Collection)
        bundle_ct = ContentType.objects.get_for_model(Bundle)
        
        # Get distinct object IDs for each content type
        collection_ids = S3ResourceLocation.objects.filter(content_type=collection_ct).values_list('object_id', flat=True).distinct()
        bundle_ids = S3ResourceLocation.objects.filter(content_type=bundle_ct).values_list('object_id', flat=True).distinct()
        
        missing_collections = []
        missing_bundles = []
        
        # Check each Collection ID
        for obj_id in collection_ids:
            try:
                if not Collection.objects.filter(pk=obj_id).exists():
                    missing_collections.append(obj_id)
            except (ValueError, TypeError):
                pass
        
        # Check each Bundle ID
        for obj_id in bundle_ids:
            try:
                if not Bundle.objects.filter(pk=obj_id).exists():
                    missing_bundles.append(obj_id)
            except (ValueError, TypeError):
                pass
        
        return missing_collections, missing_bundles 