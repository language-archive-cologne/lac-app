import os
import tempfile
import shutil
import json
import pytest
import boto3
from moto import mock_aws
from pathlib import Path
from unittest.mock import patch, MagicMock

from lacos.storage.services.bucket_service import BucketService

# Use a static bucket name for testing
TEST_BUCKET_NAME = 'test-bucket'

@pytest.fixture
def mock_s3():
    """Set up mock AWS S3 environment"""
    with mock_aws():
        # Create S3 client with mock credentials
        s3 = boto3.client(
            's3',
            aws_access_key_id='testing',
            aws_secret_access_key='testing',
            region_name='us-east-1'
        )
        # Create test bucket
        s3.create_bucket(Bucket=TEST_BUCKET_NAME)
        yield s3

@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests and clean it up afterwards"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture
def mock_bucket_service(mock_s3):
    """Create a BucketService instance with mock settings"""
    service = BucketService()
    
    # Set the test bucket for all services
    service.ingest_bucket = TEST_BUCKET_NAME
    service.production_bucket = TEST_BUCKET_NAME
    service.s3_client = mock_s3
    
    # Configure child services
    # Collection service
    service.collection_service.s3_client = mock_s3
    service.collection_service.ingest_bucket = TEST_BUCKET_NAME
    service.collection_service.production_bucket = TEST_BUCKET_NAME
    
    # Upload service and its collection service
    service.upload_service.s3_client = mock_s3
    service.upload_service.ingest_bucket = TEST_BUCKET_NAME
    service.upload_service.production_bucket = TEST_BUCKET_NAME
    service.upload_service.collection_service.s3_client = mock_s3
    service.upload_service.collection_service.ingest_bucket = TEST_BUCKET_NAME
    service.upload_service.collection_service.production_bucket = TEST_BUCKET_NAME
    
    # OCFL service
    service.ocfl_service.s3_client = mock_s3
    service.ocfl_service.ingest_bucket = TEST_BUCKET_NAME
    service.ocfl_service.production_bucket = TEST_BUCKET_NAME
    
    # Verify all services have the correct configuration
    assert service.s3_client == mock_s3
    assert service.ingest_bucket == TEST_BUCKET_NAME
    assert service.collection_service.s3_client == mock_s3
    assert service.upload_service.s3_client == mock_s3
    assert service.upload_service.collection_service.s3_client == mock_s3
    assert service.ocfl_service.s3_client == mock_s3
    
    return service

@patch('lacos.storage.services.base_storage_service.BaseStorageService.ensure_bucket_exists')
def test_bucket_service_initialization(mock_ensure_bucket):
    """Test that BucketService initializes with the correct internal services"""
    # Mock ensure_bucket_exists to return True
    mock_ensure_bucket.return_value = True
    
    # Initialize the service
    service = BucketService()
    
    # Verify that internal services are properly initialized
    assert service.collection_service is not None
    assert service.upload_service is not None
    assert service.s3_client is not None
    
    # Verify bucket check was called
    assert mock_ensure_bucket.call_count == 2

def test_delegation_to_collection_service(mock_bucket_service):
    """Test that collection-related methods properly delegate to CollectionService"""
    # Save the original method for restoration
    original_method = mock_bucket_service.collection_service.is_collection_path
    
    # Track calls to the method
    calls = []
    
    # Define a wrapper function that tracks calls and then delegates to the original
    def tracking_wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return original_method(*args, **kwargs)
    
    # Replace the original method with our tracking wrapper
    mock_bucket_service.collection_service.is_collection_path = tracking_wrapper
    
    try:
        # Call the method on BucketService
        path = "collection/collection"
        result = mock_bucket_service.is_collection_path(path)
        
        # Verify the method was delegated with correct arguments
        assert len(calls) == 1, "Method should be called exactly once"
        args, kwargs = calls[0]
        assert args[0] == path, "Argument should be the test path"
    finally:
        # Restore the original method
        mock_bucket_service.collection_service.is_collection_path = original_method

def test_delegation_to_upload_service(mock_bucket_service, temp_dir):
    """Test that upload-related methods properly delegate to UploadService"""
    # Create a test directory
    test_dir = os.path.join(temp_dir, "test_folder")
    os.makedirs(test_dir, exist_ok=True)
    with open(os.path.join(test_dir, "test.txt"), "w") as f:
        f.write("test content")
    
    # Save the original method for restoration
    original_method = mock_bucket_service.upload_service.upload_folder_to_bucket
    
    # Track calls to the method
    calls = []
    
    # Define a wrapper function that tracks calls and then delegates to the original
    def tracking_wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return original_method(*args, **kwargs)
    
    # Replace the original method with our tracking wrapper
    mock_bucket_service.upload_service.upload_folder_to_bucket = tracking_wrapper
    
    try:
        # Call the method on BucketService
        mock_bucket_service.upload_folder_to_bucket(test_dir, TEST_BUCKET_NAME)
        
        # Verify the method was delegated with correct arguments
        assert len(calls) == 1, "Method should be called exactly once"
        args, kwargs = calls[0]
        assert args[0] == test_dir, "First argument should be the test directory"
        assert args[1] == TEST_BUCKET_NAME, "Second argument should be the bucket name"
    finally:
        # Restore the original method
        mock_bucket_service.upload_service.upload_folder_to_bucket = original_method

def test_integration_upload_and_check_collection(mock_s3, mock_bucket_service, temp_dir):
    """Test integration between uploading a collection and detecting it"""
    # Create collection directory structure
    collection_name = "test_collection"
    collection_dir = Path(temp_dir) / collection_name
    collection_subdir = collection_dir / collection_name
    os.makedirs(collection_subdir, exist_ok=True)
    
    # Create OCFL marker and acl.json
    with open(collection_subdir / "0=ocfl_object_1.0", "w") as f:
        f.write("ocfl_object_1.0")
    with open(collection_subdir / "acl.json", "w") as f:
        json.dump({"permissions": []}, f)
    
    # Upload the collection
    result = mock_bucket_service.upload_folder_to_bucket(str(collection_dir), TEST_BUCKET_NAME)
    assert result["success"], "Failed to upload collection folder"
    
    # Check if the path is recognized as a collection
    collection_path = f"{collection_name}/{collection_name}"
    is_collection = mock_bucket_service.is_collection_path(collection_path)
    assert is_collection, "Failed to recognize collection path"
    
    # Check folder structure
    folder_structure = mock_bucket_service.get_folder_structure(TEST_BUCKET_NAME, f"{collection_name}/")
    assert folder_structure is not None, "Failed to get folder structure"
    assert folder_structure["name"] == collection_name, "Collection not found in folder structure"

def test_direct_upload_and_collection_recognition(mock_s3, mock_bucket_service):
    """Test direct upload of files and collection recognition"""
    # Setup collection path and files
    collection_name = "test_collection"
    files = [
        {"name": "0=ocfl_object_1.0", "content": "ocfl_object_1.0"},
        {"name": "acl.json", "content": json.dumps({"permissions": []})},
        {"name": "test.txt", "content": "test content"}
    ]
    
    # Create uploaded files and paths
    uploaded_files = []
    file_paths = {}
    for file_info in files:
        from django.core.files.uploadedfile import SimpleUploadedFile
        name = file_info["name"]
        content = file_info["content"]
        upload_file = SimpleUploadedFile(
            name=name,
            content=content.encode() if isinstance(content, str) else content,
            content_type="text/plain"
        )
        uploaded_files.append(upload_file)
        file_paths[name] = f"{collection_name}/{collection_name}/{name}"
    
    # Override bucket settings for the upload service as well
    mock_bucket_service.upload_service.s3_client = mock_s3
    mock_bucket_service.upload_service.ingest_bucket = TEST_BUCKET_NAME
    mock_bucket_service.upload_service.production_bucket = TEST_BUCKET_NAME
    
    # Upload files directly
    result = mock_bucket_service.upload_files_directly(
        uploaded_files,
        collection_name,
        TEST_BUCKET_NAME,
        file_paths
    )
    
    # Add detailed error reporting
    if not result.get("success", False):
        print(f"Upload failed with details: {result}")
        if "error" in result:
            print(f"Error message: {result['error']}")
        if "failed_files" in result:
            for ff in result.get("failed_files", []):
                print(f"Failed file: {ff}")
    
    assert result["success"], f"Failed to upload files directly: {result.get('error', 'Unknown error')}"
    
    # Verify collection is recognized
    collection_path = f"{collection_name}/{collection_name}"
    is_collection = mock_bucket_service.is_collection_path(collection_path)
    assert is_collection, "Failed to recognize collection path after direct upload"
    
    # List all objects in the bucket for debugging if needed
    try:
        response = mock_s3.list_objects_v2(
            Bucket=TEST_BUCKET_NAME,
            Prefix=f"{collection_name}/"
        )
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        print(f"Found {len(keys)} keys in bucket:")
        for key in keys:
            print(f"  - {key}")
    except Exception as e:
        print(f"Error listing bucket contents: {e}")
        keys = []
    
    # Verify critical files are at both levels
    response = mock_s3.list_objects_v2(
        Bucket=TEST_BUCKET_NAME,
        Prefix=f"{collection_name}/"
    )
    keys = [obj["Key"] for obj in response.get("Contents", [])]
    
    # Check collection level
    assert f"{collection_name}/0=ocfl_object_1.0" in keys, "OCFL marker not found at parent level"
    assert f"{collection_name}/acl.json" in keys, "acl.json not found at parent level"
    
    # Check subcollection level
    assert f"{collection_path}/0=ocfl_object_1.0" in keys, "OCFL marker not found at collection level"
    assert f"{collection_path}/acl.json" in keys, "acl.json not found at collection level"
    assert f"{collection_path}/test.txt" in keys, "test.txt not found at collection level"

def test_service_configuration_consistency(mock_s3, mock_bucket_service):
    """Test that all services in the chain share the same configuration."""
    # All services should use the same S3 client
    assert mock_bucket_service.s3_client == mock_s3
    assert mock_bucket_service.collection_service.s3_client == mock_s3
    assert mock_bucket_service.upload_service.s3_client == mock_s3
    assert mock_bucket_service.upload_service.collection_service.s3_client == mock_s3
    assert mock_bucket_service.ocfl_service.s3_client == mock_s3
    
    # All services should use the same bucket names
    assert mock_bucket_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.collection_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.collection_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.collection_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.collection_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.ocfl_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.ocfl_service.production_bucket == TEST_BUCKET_NAME