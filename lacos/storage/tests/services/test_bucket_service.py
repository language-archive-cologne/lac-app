import pytest
from unittest.mock import patch, MagicMock

from django.core.cache import cache

from botocore.exceptions import EndpointConnectionError
from django.test import override_settings

from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.bucket_service import BucketService

# Import constants from test_constants.py
from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

# We can use the mock_s3 and temp_dir fixtures from conftest.py
# Only define fixtures that aren't in conftest.py

@pytest.fixture
def mock_bucket_service(mock_s3):
    """Create a BucketService instance with mock settings"""
    service = BucketService(skip_bucket_check=True)
    
    # Set the test bucket for all services
    service.ingest_bucket = TEST_INGEST_BUCKET
    service.production_bucket = TEST_PRODUCTION_BUCKET
    service.s3_client = mock_s3
    
    # Configure child services
    # Collection service
    service.collection_service.s3_client = mock_s3
    service.collection_service.ingest_bucket = TEST_INGEST_BUCKET
    service.collection_service.production_bucket = TEST_PRODUCTION_BUCKET
    
    # Upload service
    service.upload_service.s3_client = mock_s3
    service.upload_service.ingest_bucket = TEST_INGEST_BUCKET
    service.upload_service.production_bucket = TEST_PRODUCTION_BUCKET
    
    # OCFL service
    service.ocfl_service.s3_client = mock_s3
    service.ocfl_service.ingest_bucket = TEST_INGEST_BUCKET
    service.ocfl_service.production_bucket = TEST_PRODUCTION_BUCKET
    
    # Verify all services have the correct configuration
    assert service.s3_client == mock_s3
    assert service.ingest_bucket == TEST_INGEST_BUCKET
    assert service.collection_service.s3_client == mock_s3
    assert service.upload_service.s3_client == mock_s3
    assert service.ocfl_service.s3_client == mock_s3
    
    return service

@patch('lacos.storage.services.base_storage_service.BaseStorageService.ensure_bucket_exists')
def test_bucket_service_initialization(mock_ensure_bucket):
    """Test that BucketService initializes with the correct internal services"""
    # Mock ensure_bucket_exists to return True
    mock_ensure_bucket.return_value = True
    
    # Initialize the service with skip_bucket_check=True
    service = BucketService(skip_bucket_check=True)
    
    # Verify that internal services are properly initialized
    assert service.collection_service is not None
    assert service.upload_service is not None
    assert service.s3_client is not None
    
    # Verify bucket check was not called since skip_bucket_check is True
    assert mock_ensure_bucket.call_count == 0

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

def test_service_configuration_consistency(mock_s3, mock_bucket_service):
    """Test that all services in the chain share the same configuration."""
    # All services should use the same S3 client
    assert mock_bucket_service.s3_client == mock_s3
    assert mock_bucket_service.collection_service.s3_client == mock_s3
    assert mock_bucket_service.upload_service.s3_client == mock_s3
    assert mock_bucket_service.ocfl_service.s3_client == mock_s3
    
    # All services should use the same bucket names
    assert mock_bucket_service.ingest_bucket == TEST_INGEST_BUCKET
    assert mock_bucket_service.production_bucket == TEST_PRODUCTION_BUCKET
    assert mock_bucket_service.collection_service.ingest_bucket == TEST_INGEST_BUCKET
    assert mock_bucket_service.collection_service.production_bucket == TEST_PRODUCTION_BUCKET
    assert mock_bucket_service.upload_service.ingest_bucket == TEST_INGEST_BUCKET
    assert mock_bucket_service.upload_service.production_bucket == TEST_PRODUCTION_BUCKET
    assert mock_bucket_service.ocfl_service.ingest_bucket == TEST_INGEST_BUCKET
    assert mock_bucket_service.ocfl_service.production_bucket == TEST_PRODUCTION_BUCKET

def test_direct_move_to_production(mock_s3, mock_bucket_service):
    """Test direct move to production without OCFL transformation."""
    # Create test directory structure
    test_prefix = "test-collection/"
    test_files = [
        test_prefix + "file1.txt",
        test_prefix + "file2.txt",
        test_prefix + "subdir/file3.txt",
        test_prefix + "subdir/file4.txt"
    ]
    
    # Use imported constants instead of hardcoded values
    ingest_bucket = TEST_INGEST_BUCKET
    production_bucket = TEST_PRODUCTION_BUCKET
    
    # Upload test files to ingest bucket
    for file_path in test_files:
        mock_s3.put_object(
            Bucket=ingest_bucket,
            Key=file_path,
            Body=f"Content of {file_path}"
        )
    
    # Temporarily set the bucket names
    original_ingest_bucket = mock_bucket_service.ingest_bucket
    original_production_bucket = mock_bucket_service.production_bucket
    mock_bucket_service.ingest_bucket = ingest_bucket
    mock_bucket_service.production_bucket = production_bucket
    
    try:
        # Call the direct_move_to_production method
        result = mock_bucket_service.direct_move_to_production(test_prefix)
        
        # Verify the result
        assert result["success"] is True
        assert "Successfully moved" in result["message"]
        assert len(test_files) == int(result["message"].split("(")[1].split(" ")[0])
        
        # Verify files exist in production bucket with the same content
        for file_path in test_files:
            # Get the file content from the ingest bucket
            response = mock_s3.get_object(Bucket=ingest_bucket, Key=file_path)
            ingest_content = response["Body"].read().decode("utf-8")
            
            # Get the file content from the production bucket
            response = mock_s3.get_object(Bucket=production_bucket, Key=file_path)
            production_content = response["Body"].read().decode("utf-8")
            
            # Verify the content is the same
        assert ingest_content == production_content
    finally:
        # Restore the original bucket names
        mock_bucket_service.ingest_bucket = original_ingest_bucket
        mock_bucket_service.production_bucket = original_production_bucket


@override_settings(S3_WORKSPACE_BUCKETS=["fallback-ingest", "fallback-production"])
def test_get_all_accessible_buckets_returns_defaults_when_s3_unreachable():
    """Ensure the bucket service falls back gracefully when S3 cannot be reached."""
    # Reset singleton instances to ensure a clean initialization for this test
    BaseStorageService._instance = None
    BucketService._instance = None

    service = BucketService(skip_bucket_check=True)
    service.is_minio = False
    cache.delete("storage:bucket-names")

    failing_client = MagicMock()
    failing_client.head_bucket.side_effect = EndpointConnectionError(
        endpoint_url="https://rdsp.fds.uni-koeln.de"
    )
    service.s3_client = failing_client

    buckets = service.get_all_accessible_buckets(force_refresh=True)

    assert buckets == ["fallback-ingest", "fallback-production"]
    failing_client.head_bucket.assert_called_once_with(Bucket="fallback-ingest")

    # Leave singletons reset so other tests get a fresh instance
    BaseStorageService._instance = None
    BucketService._instance = None


@override_settings(S3_WORKSPACE_BUCKETS=["bucket-a", "bucket-b"])
def test_get_all_accessible_buckets_filters_to_workspace_on_s3(settings):
    """Verify we only expose configured workspace buckets when using external S3."""
    BaseStorageService._instance = None
    BucketService._instance = None

    service = BucketService(skip_bucket_check=True)
    service.is_minio = False
    service.ingest_bucket = "bucket-a"
    service.production_bucket = "bucket-b"
    service.workspace_buckets = ["bucket-a", "bucket-b"]
    cache.delete("storage:bucket-names")

    s3_client = MagicMock()
    s3_client.head_bucket.return_value = None
    service.s3_client = s3_client

    result = service.get_all_accessible_buckets(force_refresh=True)

    assert result == ["bucket-a", "bucket-b"]
    s3_client.head_bucket.assert_any_call(Bucket="bucket-a")
    s3_client.head_bucket.assert_any_call(Bucket="bucket-b")

    BaseStorageService._instance = None
    BucketService._instance = None
