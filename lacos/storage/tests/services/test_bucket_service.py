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
        
        # Configure bucket policy to allow all operations
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "PublicReadGetObject",
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{TEST_BUCKET_NAME}",
                        f"arn:aws:s3:::{TEST_BUCKET_NAME}/*"
                    ]
                }
            ]
        }
        s3.put_bucket_policy(Bucket=TEST_BUCKET_NAME, Policy=json.dumps(bucket_policy))
        
        # Configure CORS
        cors_configuration = {
            'CORSRules': [{
                'AllowedHeaders': ['*'],
                'AllowedMethods': ['GET', 'PUT', 'POST', 'DELETE'],
                'AllowedOrigins': ['*'],
                'ExposeHeaders': ['ETag']
            }]
        }
        s3.put_bucket_cors(Bucket=TEST_BUCKET_NAME, CORSConfiguration=cors_configuration)
        
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
    service = BucketService(skip_bucket_check=True)
    
    # Set the test bucket for all services
    service.ingest_bucket = TEST_BUCKET_NAME
    service.production_bucket = TEST_BUCKET_NAME
    service.s3_client = mock_s3
    
    # Configure child services
    # Collection service
    service.collection_service.s3_client = mock_s3
    service.collection_service.ingest_bucket = TEST_BUCKET_NAME
    service.collection_service.production_bucket = TEST_BUCKET_NAME
    
    # Upload service
    service.upload_service.s3_client = mock_s3
    service.upload_service.ingest_bucket = TEST_BUCKET_NAME
    service.upload_service.production_bucket = TEST_BUCKET_NAME
    
    # OCFL service
    service.ocfl_service.s3_client = mock_s3
    service.ocfl_service.ingest_bucket = TEST_BUCKET_NAME
    service.ocfl_service.production_bucket = TEST_BUCKET_NAME
    
    # Verify all services have the correct configuration
    assert service.s3_client == mock_s3
    assert service.ingest_bucket == TEST_BUCKET_NAME
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

# Note: The upload-related tests have been removed since BucketService no longer provides 
# these methods directly. The UploadService should be tested in its own test file.

def test_service_configuration_consistency(mock_s3, mock_bucket_service):
    """Test that all services in the chain share the same configuration."""
    # All services should use the same S3 client
    assert mock_bucket_service.s3_client == mock_s3
    assert mock_bucket_service.collection_service.s3_client == mock_s3
    assert mock_bucket_service.upload_service.s3_client == mock_s3
    assert mock_bucket_service.ocfl_service.s3_client == mock_s3
    
    # All services should use the same bucket names
    assert mock_bucket_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.collection_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.collection_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.upload_service.production_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.ocfl_service.ingest_bucket == TEST_BUCKET_NAME
    assert mock_bucket_service.ocfl_service.production_bucket == TEST_BUCKET_NAME