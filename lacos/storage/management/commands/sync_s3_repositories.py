from django.core.management.base import BaseCommand
from django.conf import settings
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.storage.services import S3Service, ACFLService

class Command(BaseCommand):
    help = 'Sync S3 locations and ACFL permissions for collections and bundles'
    
    def add_arguments(self, parser):
        parser.add_argument('--collection', type=str, help='Collection ID to sync')
        parser.add_argument('--all', action='store_true', help='Sync all collections')
        parser.add_argument('--bucket', type=str, help='S3 bucket name (defaults to settings.S3_BUCKET)')
        parser.add_argument('--skip-bundles', action='store_true', help='Skip syncing bundles')
        parser.add_argument('--skip-acfl', action='store_true', help='Skip syncing ACFL permissions')
    
    def handle(self, *args, **options):
        # Get the S3 bucket
        bucket = options.get('bucket') or getattr(settings, 'S3_BUCKET', 'my-bucket')
        
        # Determine which collections to sync
        if options.get('collection'):
            try:
                collection = Collection.objects.get(id=options['collection'])
                self.sync_collection(collection, bucket, options)
            except Collection.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Collection with ID {options['collection']} not found"))
                return
        elif options.get('all'):
            collections = Collection.objects.all()
            for collection in collections:
                self.sync_collection(collection, bucket, options)
        else:
            self.stdout.write(self.style.ERROR('Please specify --collection or --all'))
            return
    
    def sync_collection(self, collection, bucket, options):
        """Sync a collection with its S3 location and ACFL permissions"""
        self.stdout.write(f"Syncing collection {collection.id}")
        
        # Construct the S3 path for the collection
        collection_path = S3Service.construct_s3_path(collection)
        if not collection_path:
            collection_path = f"collections/{collection.id}/"
        
        # Register S3 location
        try:
            S3Service.register_s3_location(
                collection,
                bucket=bucket,
                key=collection_path,
                pid_url=f"https://handle.net/10.123/collection-{collection.id}"  # Example PID - adjust as needed
            )
            self.stdout.write(self.style.SUCCESS(f"  Registered S3 location for collection {collection.id}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  Error registering S3 location for collection {collection.id}: {e}"))
        
        # Register ACFL file
        if not options.get('skip_acfl'):
            try:
                collection.register_acfl_file(
                    bucket=bucket,
                    key=f"{collection_path}acfl.json"
                )
                self.stdout.write(self.style.SUCCESS(f"  Registered ACFL file for collection {collection.id}"))
                
                # Refresh permissions
                collection.refresh_acfl_permissions()
                self.stdout.write(self.style.SUCCESS(f"  Refreshed ACFL permissions for collection {collection.id}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error registering ACFL file for collection {collection.id}: {e}"))
        
        # Sync bundles in this collection
        if not options.get('skip_bundles'):
            bundles = Bundle.objects.filter(structural_info__is_member_of_collection=collection)
            for bundle in bundles:
                self.sync_bundle(bundle, bucket, options)
    
    def sync_bundle(self, bundle, bucket, options):
        """Sync a bundle with its S3 location and ACFL permissions"""
        self.stdout.write(f"  Syncing bundle {bundle.id}")
        
        # Construct the S3 path for the bundle
        bundle_path = S3Service.construct_s3_path(bundle)
        if not bundle_path:
            collection = bundle.structural_info.is_member_of_collection
            bundle_path = f"collections/{collection.id}/bundles/{bundle.id}/"
        
        # Register S3 location
        try:
            S3Service.register_s3_location(
                bundle,
                bucket=bucket,
                key=bundle_path,
                pid_url=f"https://handle.net/10.123/bundle-{bundle.id}"  # Example PID - adjust as needed
            )
            self.stdout.write(self.style.SUCCESS(f"    Registered S3 location for bundle {bundle.id}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    Error registering S3 location for bundle {bundle.id}: {e}"))
        
        # Register ACFL file
        if not options.get('skip_acfl'):
            try:
                bundle.register_acfl_file(
                    bucket=bucket,
                    key=f"{bundle_path}acfl.json"
                )
                self.stdout.write(self.style.SUCCESS(f"    Registered ACFL file for bundle {bundle.id}"))
                
                # Refresh permissions
                bundle.refresh_acfl_permissions()
                self.stdout.write(self.style.SUCCESS(f"    Refreshed ACFL permissions for bundle {bundle.id}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Error registering ACFL file for bundle {bundle.id}: {e}")) 