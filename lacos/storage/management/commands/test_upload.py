import os
import tempfile
import json
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from lacos.storage.services.bucket_service import BucketService

class Command(BaseCommand):
    help = 'Test the upload and transformation of collections and bundles'

    def add_arguments(self, parser):
        parser.add_argument('--test-type', choices=['collection', 'bundle'], 
                            default='collection', help='Type of test to run')

    def handle(self, *args, **options):
        test_type = options.get('test_type', 'collection')
        
        # Create bucket service
        bucket_service = BucketService()
        
        # Clean up any previous test data
        self._cleanup_test_data(bucket_service)
        
        # Use a temp directory for the test
        with tempfile.TemporaryDirectory() as temp_dir:
            self.stdout.write(f"Created temporary directory: {temp_dir}")
            
            if test_type == 'collection':
                # Test collection upload (same parent/child names)
                collection_name = "test_collection"
                self._test_collection_upload(bucket_service, temp_dir, collection_name)
            else:
                # Test bundle upload (different parent/child names)
                collection_name = "test_collection"
                bundle_name = "test_bundle"
                self._test_bundle_upload(bucket_service, temp_dir, collection_name, bundle_name)
    
    def _cleanup_test_data(self, bucket_service):
        """Clean up any test data from previous runs"""
        self.stdout.write("Cleaning up previous test data...")
        
        # Delete test_collection and its contents
        try:
            result = bucket_service.delete_object(
                bucket_service.ingest_bucket,
                "test_collection/",
                is_directory=True
            )
            if result["success"]:
                self.stdout.write(self.style.SUCCESS(f"Deleted {result.get('deleted_objects', 0)} objects from previous tests"))
            else:
                self.stdout.write(self.style.WARNING(f"Cleanup warning: {result.get('error', 'Unknown error')}"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error during cleanup: {str(e)}"))
    
    def _test_collection_upload(self, bucket_service, temp_dir, collection_name):
        """Test uploading a collection with identical parent/child directory names"""
        self.stdout.write(self.style.NOTICE(f"Testing collection upload with {collection_name}/{collection_name}"))
        
        # Create parent directory
        parent_dir = Path(temp_dir) / collection_name
        # Create child directory with same name
        collection_dir = parent_dir / collection_name
        os.makedirs(collection_dir, exist_ok=True)
        
        # Create OCFL marker
        with open(collection_dir / "0=ocfl_object_1.0", "w") as f:
            f.write("ocfl_object_1.0")
        
        # Create ACL file
        with open(collection_dir / "acl.json", "w") as f:
            json.dump({"permissions": []}, f)
        
        # Create a test XML file
        with open(collection_dir / f"{collection_name}.xml", "w") as f:
            f.write("<collection>Test Collection</collection>")
            
        self.stdout.write(f"Created collection structure:")
        self.stdout.write(f"  - {collection_dir}/0=ocfl_object_1.0")
        self.stdout.write(f"  - {collection_dir}/acl.json")
        self.stdout.write(f"  - {collection_dir}/{collection_name}.xml")
        
        # Upload the collection directory
        self.stdout.write(f"Uploading collection directory...")
        target_prefix = f"{collection_name}/{collection_name}"
        result = bucket_service._upload_directory(
            str(collection_dir),
            bucket_service.ingest_bucket,
            target_prefix
        )
        
        # Display results
        self.stdout.write(self.style.SUCCESS(f"Upload {'succeeded' if result['success'] else 'failed'}"))
        self.stdout.write(f"Uploaded {len(result['uploaded_files'])} files")
        
        # Check at child level
        self.stdout.write("Checking files at child level...")
        child_contents = bucket_service.list_bucket_contents(
            bucket_service.ingest_bucket, 
            target_prefix
        )
        
        child_files = [item for item in child_contents if not item.get("is_dir", False)]
        self.stdout.write(f"Found {len(child_files)} files at child level")
        for item in child_files:
            self.stdout.write(f"  - {item['name']} ({item['path']})")
        
        # Check at parent level
        self.stdout.write("Checking files at parent level...")
        parent_contents = bucket_service.list_bucket_contents(
            bucket_service.ingest_bucket, 
            collection_name
        )
        
        parent_files = [item for item in parent_contents if not item.get("is_dir", False)]
        self.stdout.write(f"Found {len(parent_files)} files at parent level")
        for item in parent_files:
            self.stdout.write(f"  - {item['name']} ({item['path']})")
        
        # Check for critical files at both levels
        ocfl_at_child = any(item["name"].startswith("0=ocfl_object_") for item in child_files)
        acl_at_child = any(item["name"] == "acl.json" for item in child_files)
        
        ocfl_at_parent = any(item["name"].startswith("0=ocfl_object_") for item in parent_files)
        acl_at_parent = any(item["name"] == "acl.json" for item in parent_files)
        
        if ocfl_at_child and acl_at_child:
            self.stdout.write(self.style.SUCCESS("✅ Critical files found at child level"))
        else:
            self.stdout.write(self.style.ERROR("❌ Critical files NOT found at child level"))
            
        if ocfl_at_parent and acl_at_parent:
            self.stdout.write(self.style.SUCCESS("✅ Critical files found at parent level"))
        else:
            self.stdout.write(self.style.ERROR("❌ Critical files NOT found at parent level"))
    
    def _test_bundle_upload(self, bucket_service, temp_dir, collection_name, bundle_name):
        """Test uploading a bundle with different parent/child directory names"""
        self.stdout.write(self.style.NOTICE(f"Testing bundle upload with {collection_name}/{bundle_name}"))
        
        # Create parent directory
        parent_dir = Path(temp_dir) / collection_name
        # Create bundle directory
        bundle_dir = parent_dir / bundle_name
        os.makedirs(bundle_dir, exist_ok=True)
        
        # Create OCFL marker
        with open(bundle_dir / "0=ocfl_object_1.0", "w") as f:
            f.write("ocfl_object_1.0")
        
        # Create ACL file
        with open(bundle_dir / "acl.json", "w") as f:
            json.dump({"permissions": []}, f)
        
        # Create a test XML file
        with open(bundle_dir / f"{bundle_name}.xml", "w") as f:
            f.write("<bundle>Test Bundle</bundle>")
            
        self.stdout.write(f"Created bundle structure:")
        self.stdout.write(f"  - {bundle_dir}/0=ocfl_object_1.0")
        self.stdout.write(f"  - {bundle_dir}/acl.json")
        self.stdout.write(f"  - {bundle_dir}/{bundle_name}.xml")
        
        # Upload the bundle directory
        self.stdout.write(f"Uploading bundle directory...")
        target_prefix = f"{collection_name}/{bundle_name}"
        result = bucket_service._upload_directory(
            str(bundle_dir),
            bucket_service.ingest_bucket,
            target_prefix
        )
        
        # Display results
        self.stdout.write(self.style.SUCCESS(f"Upload {'succeeded' if result['success'] else 'failed'}"))
        self.stdout.write(f"Uploaded {len(result['uploaded_files'])} files")
        
        # Check at bundle level
        self.stdout.write("Checking files at bundle level...")
        bundle_contents = bucket_service.list_bucket_contents(
            bucket_service.ingest_bucket, 
            target_prefix
        )
        
        bundle_files = [item for item in bundle_contents if not item.get("is_dir", False)]
        self.stdout.write(f"Found {len(bundle_files)} files at bundle level")
        for item in bundle_files:
            self.stdout.write(f"  - {item['name']} ({item['path']})")
        
        # Check at collection level
        self.stdout.write("Checking files at collection level...")
        collection_contents = bucket_service.list_bucket_contents(
            bucket_service.ingest_bucket, 
            collection_name
        )
        
        collection_files = [item for item in collection_contents if not item.get("is_dir", False)]
        self.stdout.write(f"Found {len(collection_files)} files at collection level")
        for item in collection_files:
            self.stdout.write(f"  - {item['name']} ({item['path']})")
        
        # Check for critical files at bundle level
        ocfl_at_bundle = any(item["name"].startswith("0=ocfl_object_") for item in bundle_files)
        acl_at_bundle = any(item["name"] == "acl.json" for item in bundle_files)
        
        # For bundles, we don't expect critical files at collection level
        ocfl_at_collection = any(item["name"].startswith("0=ocfl_object_") for item in collection_files)
        acl_at_collection = any(item["name"] == "acl.json" for item in collection_files)
        
        if ocfl_at_bundle and acl_at_bundle:
            self.stdout.write(self.style.SUCCESS("✅ Critical files found at bundle level"))
        else:
            self.stdout.write(self.style.ERROR("❌ Critical files NOT found at bundle level"))
            
        if not ocfl_at_collection and not acl_at_collection:
            self.stdout.write(self.style.SUCCESS("✅ No critical files found at collection level (as expected)"))
        else:
            self.stdout.write(self.style.WARNING("⚠️ Critical files found at collection level (not expected for bundles)")) 