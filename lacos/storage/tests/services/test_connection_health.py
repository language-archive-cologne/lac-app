"""
Test S3/MinIO connection health and basic operations.

This test suite verifies the connection, handshake, and basic listing
operations with detailed logging to help diagnose connection issues.
"""
import pytest
import logging

from lacos.storage.services.base_storage_service import BaseStorageService
from lacos.storage.services.bucket_service import BucketService

from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

logger = logging.getLogger(__name__)


@pytest.fixture
def health_check_service(mock_s3):
    """Create a service instance for health check testing"""
    service = BaseStorageService(skip_bucket_check=True)
    service.s3_client = mock_s3
    service.ingest_bucket = TEST_INGEST_BUCKET
    service.production_bucket = TEST_PRODUCTION_BUCKET
    return service


def test_s3_connection_handshake(health_check_service):
    """
    Test basic S3 connection handshake.

    This verifies we can establish a connection and list buckets
    before attempting any complex operations.
    """
    logger.info("=" * 80)
    logger.info("HEALTH CHECK: Testing S3 connection handshake")
    logger.info("=" * 80)

    try:
        # Attempt to list buckets - this is the simplest S3 operation
        logger.info("Attempting to list buckets...")
        response = health_check_service.s3_client.list_buckets()

        logger.info("✅ Successfully connected to S3/MinIO")
        logger.info(f"Response metadata: {response.get('ResponseMetadata', {})}")

        # Count buckets
        buckets = response.get('Buckets', [])
        bucket_count = len(buckets)

        logger.info(f"Found {bucket_count} bucket(s)")
        for idx, bucket in enumerate(buckets, 1):
            logger.info(f"  {idx}. {bucket['Name']} (created: {bucket.get('CreationDate', 'unknown')})")

        # Verify we got a valid response
        assert 'Buckets' in response, "Response should contain 'Buckets' key"
        assert isinstance(buckets, list), "Buckets should be a list"

        logger.info("✅ Connection handshake successful")

    except Exception as e:
        logger.error(f"❌ Connection handshake failed: {str(e)}")
        logger.exception("Full exception details:")
        raise


def test_bucket_count_before_listing(mock_s3, health_check_service):
    """
    Test that we can count buckets before attempting to list their contents.

    This helps identify if issues are with connection vs. with listing operations.
    """
    logger.info("=" * 80)
    logger.info("HEALTH CHECK: Counting buckets before listing")
    logger.info("=" * 80)

    # Create test buckets
    test_buckets = [TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET]

    logger.info(f"Creating {len(test_buckets)} test buckets...")
    for bucket_name in test_buckets:
        logger.info(f"  Creating bucket: {bucket_name}")
        mock_s3.create_bucket(Bucket=bucket_name)

    # List all buckets
    logger.info("Listing all buckets...")
    response = health_check_service.s3_client.list_buckets()
    buckets = response.get('Buckets', [])
    bucket_names = [b['Name'] for b in buckets]

    logger.info(f"Total buckets found: {len(buckets)}")
    for name in bucket_names:
        logger.info(f"  - {name}")

    # Verify our test buckets exist
    for bucket_name in test_buckets:
        assert bucket_name in bucket_names, f"Expected bucket '{bucket_name}' not found"
        logger.info(f"✅ Verified bucket exists: {bucket_name}")

    logger.info("✅ Bucket count verification successful")


def test_simple_bucket_listing(mock_s3, health_check_service):
    """
    Test simple bucket listing with detailed logging.

    This tests the most basic list operation to isolate pagination issues.
    """
    logger.info("=" * 80)
    logger.info("HEALTH CHECK: Testing simple bucket listing")
    logger.info("=" * 80)

    # Create bucket and add a few objects
    bucket_name = TEST_INGEST_BUCKET
    logger.info(f"Creating test bucket: {bucket_name}")
    mock_s3.create_bucket(Bucket=bucket_name)

    # Add test objects
    test_objects = [
        "folder1/",
        "folder2/",
        "file1.txt",
        "file2.txt",
    ]

    logger.info(f"Adding {len(test_objects)} test objects...")
    for obj_key in test_objects:
        logger.info(f"  Adding: {obj_key}")
        mock_s3.put_object(Bucket=bucket_name, Key=obj_key, Body=b"test content")

    # Simple list without pagination
    logger.info("Performing simple list_objects_v2 call...")
    response = mock_s3.list_objects_v2(Bucket=bucket_name)

    # Log response details
    logger.info("Response keys: %s", list(response.keys()))
    logger.info(f"KeyCount: {response.get('KeyCount', 0)}")
    logger.info(f"IsTruncated: {response.get('IsTruncated', False)}")

    contents = response.get('Contents', [])
    logger.info(f"Objects returned: {len(contents)}")
    for obj in contents:
        logger.info(f"  - {obj['Key']} ({obj.get('Size', 0)} bytes)")

    assert len(contents) > 0, "Should have returned some objects"
    logger.info("✅ Simple listing successful")


def test_listing_with_delimiter(mock_s3, health_check_service):
    """
    Test listing with delimiter to separate folders from files.

    This is the pattern used by our pagination code.
    """
    logger.info("=" * 80)
    logger.info("HEALTH CHECK: Testing listing with delimiter")
    logger.info("=" * 80)

    # Create bucket and add objects with folder structure
    bucket_name = TEST_INGEST_BUCKET
    logger.info(f"Creating test bucket: {bucket_name}")
    mock_s3.create_bucket(Bucket=bucket_name)

    # Add test objects with folder structure
    test_objects = [
        "folder1/file1.txt",
        "folder1/file2.txt",
        "folder2/file3.txt",
        "root_file.txt",
    ]

    logger.info(f"Adding {len(test_objects)} test objects with folder structure...")
    for obj_key in test_objects:
        logger.info(f"  Adding: {obj_key}")
        mock_s3.put_object(Bucket=bucket_name, Key=obj_key, Body=b"test content")

    # List with delimiter
    logger.info("Performing list_objects_v2 with Delimiter='/'...")
    response = mock_s3.list_objects_v2(Bucket=bucket_name, Delimiter="/")

    # Log response details
    logger.info("Response keys: %s", list(response.keys()))
    logger.info(f"KeyCount: {response.get('KeyCount', 0)}")

    # Files at root level
    contents = response.get('Contents', [])
    logger.info(f"Files at root: {len(contents)}")
    for obj in contents:
        logger.info(f"  File: {obj['Key']}")

    # Folders (common prefixes)
    common_prefixes = response.get('CommonPrefixes', [])
    logger.info(f"Folders at root: {len(common_prefixes)}")
    for prefix_obj in common_prefixes:
        logger.info(f"  Folder: {prefix_obj['Prefix']}")

    assert len(contents) > 0, "Should have root-level files"
    assert len(common_prefixes) > 0, "Should have folders"
    logger.info("✅ Delimiter listing successful")


def test_pagination_with_max_keys(mock_s3, health_check_service):
    """
    Test pagination behavior with MaxKeys parameter.

    This verifies the pagination interface even if moto doesn't respect it fully.
    """
    logger.info("=" * 80)
    logger.info("HEALTH CHECK: Testing pagination with MaxKeys")
    logger.info("=" * 80)

    # Create bucket and add multiple objects
    bucket_name = TEST_INGEST_BUCKET
    logger.info(f"Creating test bucket: {bucket_name}")
    mock_s3.create_bucket(Bucket=bucket_name)

    # Add enough objects to trigger pagination
    num_objects = 5
    logger.info(f"Adding {num_objects} test objects...")
    for i in range(num_objects):
        obj_key = f"file{i}.txt"
        logger.info(f"  Adding: {obj_key}")
        mock_s3.put_object(Bucket=bucket_name, Key=obj_key, Body=b"test content")

    # List with MaxKeys
    max_keys = 2
    logger.info(f"Performing list_objects_v2 with MaxKeys={max_keys}...")
    response = mock_s3.list_objects_v2(Bucket=bucket_name, MaxKeys=max_keys)

    # Log response details
    logger.info("Response keys: %s", list(response.keys()))
    logger.info(f"KeyCount: {response.get('KeyCount', 0)}")
    logger.info(f"MaxKeys: {response.get('MaxKeys', 'not set')}")
    logger.info(f"IsTruncated: {response.get('IsTruncated', False)}")
    logger.info(f"NextContinuationToken: {response.get('NextContinuationToken', 'none')}")

    contents = response.get('Contents', [])
    logger.info(f"Objects returned: {len(contents)}")
    for obj in contents:
        logger.info(f"  - {obj['Key']}")

    # Note: moto may not respect MaxKeys, but we verify the interface exists
    assert 'Contents' in response, "Response should contain Contents"
    assert 'IsTruncated' in response, "Response should contain IsTruncated flag"

    if response.get('IsTruncated'):
        logger.info("✅ Pagination triggered (has more results)")
        assert 'NextContinuationToken' in response, "Should have continuation token when truncated"
    else:
        logger.info("⚠️  Pagination not triggered (moto may not respect MaxKeys)")

    logger.info("✅ Pagination interface test successful")
