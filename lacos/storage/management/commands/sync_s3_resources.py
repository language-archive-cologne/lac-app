from django.core.management.base import BaseCommand
from django.conf import settings
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import MediaResource, WrittenResource, OtherResource
from lacos.storage.services import S3Service

class Command(BaseCommand):
    help = 'Sync S3 locations for resources (files)'
    
    def add_arguments(self, parser):
        parser.add_argument('--collection', type=str, help='Collection ID to sync resources for')
        parser.add_argument('--bundle', type=str, help='Bundle ID to sync resources for')
        parser.add_argument('--all', action='store_true', help='Sync all resources')
        parser.add_argument('--bucket', type=str, help='S3 bucket name (defaults to settings.S3_BUCKET)')
    
    def handle(self, *args, **options):
        # Get the S3 bucket
        bucket = options.get('bucket') or getattr(settings, 'S3_BUCKET', 'my-bucket')
        
        # Determine which resources to sync
        if options.get('bundle'):
            try:
                bundle = Bundle.objects.get(id=options['bundle'])
                self.sync_bundle_resources(bundle, bucket)
            except Bundle.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Bundle with ID {options['bundle']} not found"))
                return
        elif options.get('collection'):
            try:
                collection = Collection.objects.get(id=options['collection'])
                bundles = Bundle.objects.filter(structural_info__is_member_of_collection=collection)
                for bundle in bundles:
                    self.sync_bundle_resources(bundle, bucket)
            except Collection.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Collection with ID {options['collection']} not found"))
                return
        elif options.get('all'):
            # Sync all resources
            bundles = Bundle.objects.all()
            for bundle in bundles:
                self.sync_bundle_resources(bundle, bucket)
        else:
            self.stdout.write(self.style.ERROR('Please specify --collection, --bundle, or --all'))
            return
    
    def sync_bundle_resources(self, bundle, bucket):
        """Sync all resources for a bundle"""
        self.stdout.write(f"Syncing resources for bundle {bundle.id}")
        
        # Get the bundle resources
        # This depends on your model structure - adjust as needed
        resources_synced = 0
        
        # Sync media resources
        if hasattr(bundle, 'bundle_resources') and hasattr(bundle.bundle_resources, 'bundle_media_resources'):
            for resource in bundle.bundle_resources.bundle_media_resources.all():
                self.sync_resource(resource, bundle, bucket)
                resources_synced += 1
        
        # Sync written resources
        if hasattr(bundle, 'bundle_resources') and hasattr(bundle.bundle_resources, 'bundle_written_resources'):
            for resource in bundle.bundle_resources.bundle_written_resources.all():
                self.sync_resource(resource, bundle, bucket)
                resources_synced += 1
        
        # Sync other resources
        if hasattr(bundle, 'bundle_resources') and hasattr(bundle.bundle_resources, 'bundle_other_resources'):
            for resource in bundle.bundle_resources.bundle_other_resources.all():
                self.sync_resource(resource, bundle, bucket)
                resources_synced += 1
        
        self.stdout.write(self.style.SUCCESS(f"Synced {resources_synced} resources for bundle {bundle.id}"))
    
    def sync_resource(self, resource, bundle, bucket):
        """Sync a single resource"""
        # Construct the S3 key for the resource
        collection = bundle.structural_info.is_member_of_collection
        s3_key = f"collections/{collection.id}/bundles/{bundle.id}/resources/{resource.file_name}"
        
        # Register the S3 location
        try:
            S3Service.register_s3_location(
                resource,
                bucket=bucket,
                key=s3_key,
                pid_url=resource.file_pid
            )
            self.stdout.write(f"  Synced resource: {resource.file_name}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Error syncing resource {resource.file_name}: {e}")) 