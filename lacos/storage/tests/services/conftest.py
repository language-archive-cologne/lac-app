import pytest
import boto3
import os
from moto import mock_aws
import tempfile
import shutil
from django.test import override_settings

from lacos.storage.services.base_storage_service import BaseStorageService

# Import constants from test_constants using relative import
from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

@pytest.fixture(scope='function')
def aws_credentials():
    """Set up AWS credentials for testing"""
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['S3_BUCKET_NAME'] = TEST_BUCKET_NAME
    os.environ['AWS_INGEST_BUCKET_NAME'] = TEST_INGEST_BUCKET
    os.environ['AWS_PRODUCTION_BUCKET_NAME'] = TEST_PRODUCTION_BUCKET
    
    yield
    
    # Clean up
    os.environ.pop('AWS_ACCESS_KEY_ID', None)
    os.environ.pop('AWS_SECRET_ACCESS_KEY', None)
    os.environ.pop('AWS_SECURITY_TOKEN', None)
    os.environ.pop('AWS_SESSION_TOKEN', None)
    os.environ.pop('AWS_DEFAULT_REGION', None)
    os.environ.pop('S3_BUCKET_NAME', None)
    os.environ.pop('AWS_INGEST_BUCKET_NAME', None)
    os.environ.pop('AWS_PRODUCTION_BUCKET_NAME', None)

@pytest.fixture(scope='function')
def mock_s3(aws_credentials):
    """Set up mock AWS S3 environment"""
    with mock_aws():
        # Create S3 client with mock credentials
        s3 = boto3.client(
            's3',
            aws_access_key_id='testing',
            aws_secret_access_key='testing',
            region_name='us-east-1'
        )
        # Create test buckets
        s3.create_bucket(Bucket=TEST_BUCKET_NAME)
        s3.create_bucket(Bucket=TEST_INGEST_BUCKET)
        s3.create_bucket(Bucket=TEST_PRODUCTION_BUCKET)
        yield s3

@pytest.fixture(scope='function')
def acl_sync_service(mock_s3):
    """ACLService singleton wired to the moto S3 client and test bucket."""
    from django.core.cache import cache

    from lacos.storage.services.acl_service import ACLService
    from lacos.storage.services.resource_mapping_service import ResourceMappingService

    original_sync = ACLService._instance
    original_mapping = ResourceMappingService._instance
    ACLService._instance = None
    ResourceMappingService._instance = None
    cache.clear()
    try:
        service = ACLService()
        service.s3_client = mock_s3
        service.production_bucket = TEST_BUCKET_NAME
        service.set_client_and_buckets(service.resource_mapping)
        yield service
    finally:
        cache.clear()
        ACLService._instance = original_sync
        ResourceMappingService._instance = original_mapping

@pytest.fixture(scope='function')
def temp_dir():
    """Create a temporary directory for tests and clean it up afterwards"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)

@pytest.fixture(scope='function')
def mock_base_service(mock_s3):
    """Create a BaseStorageService instance with mock settings"""
    service = BaseStorageService(skip_bucket_check=True)
    # Override the bucket names for testing
    service.ingest_bucket = TEST_INGEST_BUCKET
    service.production_bucket = TEST_PRODUCTION_BUCKET
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    if hasattr(service, 'presigned_client'):
        service.presigned_client = mock_s3
    return service
