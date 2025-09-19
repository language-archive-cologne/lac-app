"""
Test bucket creation functionality.
"""
import pytest
from unittest.mock import patch, MagicMock
from lacos.storage.services.bucket_service import BucketService


@pytest.mark.django_db
def test_bucket_creation_success():
    """Test successful bucket creation."""
    with patch.object(BucketService, 'ensure_bucket_exists', return_value=True):
        bucket_service = BucketService()

        # Mock the workspace buckets to simulate a clean state
        bucket_service.workspace_buckets = ['ingest', 'production']
        # Note: ocfl_buckets is now a property that returns all accessible buckets

        result = bucket_service.create_bucket('test-bucket', enable_ocfl=True)

        assert result['success'] is True
        assert result['bucket_name'] == 'test-bucket'
        assert result['ocfl_enabled'] is True
        assert 'test-bucket' in bucket_service.workspace_buckets
        # Note: ocfl_buckets now queries MinIO directly, so mocked buckets won't appear there


@pytest.mark.django_db
def test_bucket_creation_duplicate():
    """Test bucket creation with duplicate name."""
    bucket_service = BucketService()

    # Mock existing bucket
    bucket_service.workspace_buckets = ['ingest', 'production', 'existing-bucket']

    result = bucket_service.create_bucket('existing-bucket')

    assert result['success'] is False
    assert 'already exists' in result['error']


@pytest.mark.django_db
def test_bucket_creation_invalid_name():
    """Test bucket creation with invalid name."""
    bucket_service = BucketService()

    result = bucket_service.create_bucket('invalid bucket name!')

    assert result['success'] is False
    assert 'Invalid bucket name' in result['error']


@pytest.mark.django_db
def test_bucket_creation_s3_failure():
    """Test bucket creation when S3 operation fails."""
    with patch.object(BucketService, 'ensure_bucket_exists', return_value=False):
        bucket_service = BucketService()
        bucket_service.workspace_buckets = ['ingest', 'production']

        result = bucket_service.create_bucket('test-bucket')

        assert result['success'] is False
        assert 'Failed to create bucket' in result['error']