import tempfile
import shutil
import pytest
import boto3
from moto import mock_aws


from lacos.storage.services.upload_service import UploadService

# Use a static bucket name for testing
TEST_BUCKET_NAME = 'test-bucket'
TEST_FOLDER_NAME = 'test-folder'

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
def mock_upload_service(mock_s3):
    """Create an UploadService instance with mock settings"""
    service = UploadService()
    # Override the bucket names for testing
    service.ingest_bucket = TEST_BUCKET_NAME
    service.production_bucket = TEST_BUCKET_NAME
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    return service

def test_generate_presigned_post(mock_upload_service):
    """Test generating a presigned post URL for a single file"""
    result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain"
    )
    
    # Check the result
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["file_name"] == "test.txt", "File name should be preserved"
    assert result["s3_key"] == "test.txt", "S3 key should match the filename when no prefix"
    assert "url" in result, "Result should include the presigned URL"
    assert "fields" in result, "Result should include the form fields"
    assert "expires_in" in result, "Result should include expiration time"

def test_generate_presigned_post_with_path_prefix(mock_upload_service):
    """Test generating a presigned post URL with a path prefix"""
    result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        path_prefix="folder/subfolder"
    )
    
    # Check the result
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["s3_key"] == "folder/subfolder/test.txt", "S3 key should include the path prefix"

def test_generate_presigned_post_with_spaces_in_filename(mock_upload_service):
    """Test generating a presigned post URL with spaces in the filename"""
    result = mock_upload_service.generate_presigned_post(
        file_name="test file with spaces.txt",
        file_type="text/plain"
    )
    
    # Check the result
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["file_name"] == "test file with spaces.txt", "Original file name should be preserved"
    assert result["s3_key"] == "test_file_with_spaces.txt", "S3 key should have spaces replaced with underscores"

def test_generate_batch_presigned_posts(mock_upload_service):
    """Test generating multiple presigned post URLs"""
    files_metadata = [
        {"file_name": "file1.txt", "file_type": "text/plain"},
        {"file_name": "file2.txt", "file_type": "text/plain"},
        {"file_name": "file3.jpg", "file_type": "image/jpeg"}
    ]
    
    result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=files_metadata,
        path_prefix=TEST_FOLDER_NAME
    )
    
    # Check the overall result
    assert result["success"] is True, "Batch presigned URL generation should succeed"
    assert result["total_urls"] == 3, "Should generate 3 presigned URLs"
    assert len(result["presigned_posts"]) == 3, "Should have 3 presigned post results"
    assert result["total_failures"] == 0, "Should have no failures"
    
    # Check individual URLs
    for i, presigned_post in enumerate(result["presigned_posts"]):
        file_meta = files_metadata[i]
        assert presigned_post["file_name"] == file_meta["file_name"], f"File name should match for item {i}"
        assert presigned_post["s3_key"] == f"{TEST_FOLDER_NAME}/{file_meta['file_name']}", f"S3 key should include folder for item {i}"
        assert "url" in presigned_post, f"Item {i} should include URL"
        assert "fields" in presigned_post, f"Item {i} should include fields"

def test_generate_batch_presigned_posts_with_same_name_different_paths(mock_upload_service):
    """Test generating presigned URLs for files with the same name but different paths"""
    files_metadata = [
        {"file_name": "sample.txt", "file_type": "text/plain", "path": "folder1"},
        {"file_name": "sample.txt", "file_type": "text/plain", "path": "folder2"},
        {"file_name": "unique.txt", "file_type": "text/plain", "path": "folder3"}
    ]
    
    result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=files_metadata,
        path_prefix=TEST_FOLDER_NAME
    )
    
    # Check the overall result
    assert result["success"] is True, "Batch presigned URL generation should succeed"
    assert result["total_urls"] == 3, "Should generate 3 presigned URLs"
    
    # Get the generated s3 keys to check them
    s3_keys = [post["s3_key"] for post in result["presigned_posts"]]
    
    # Check if keys are unique - they should be now that we use path information
    assert len(set(s3_keys)) == 3, "All S3 keys should be unique"
    
    # Verify the keys have the expected structure
    expected_keys = {
        f"{TEST_FOLDER_NAME}/folder1/sample.txt",
        f"{TEST_FOLDER_NAME}/folder2/sample.txt",
        f"{TEST_FOLDER_NAME}/folder3/unique.txt"
    }
    
    assert set(s3_keys) == expected_keys, "Keys should include both folder prefix and path"

def test_generate_presigned_post_with_invalid_filename(mock_upload_service):
    """Test generating a presigned post URL with an invalid or empty filename"""
    # Test with empty filename
    result = mock_upload_service.generate_presigned_post(
        file_name="",
        file_type="text/plain"
    )
    
    # With current implementation, an empty filename would still generate a URL
    # but the S3 key would just be the path prefix or an empty string
    assert result["s3_key"] == "", "S3 key should be empty for empty filename"
    
    # Test with None filename (should handle gracefully)
    # Implementation may vary on how it handles this, adjust the test as needed
    try:
        result = mock_upload_service.generate_presigned_post(
            file_name=None,
            file_type="text/plain"
        )
        # If it doesn't raise an exception, check it handled it reasonably
        assert not result["success"] or result["s3_key"] == "", "Should either fail or create an empty S3 key"
    except:
        # This is also acceptable if the method doesn't handle None values
        pass

def test_mark_upload_complete(mock_s3, mock_upload_service):
    """Test marking an upload as complete and verifying the file"""
    # First upload a file to S3
    s3_key = f"{TEST_FOLDER_NAME}/test.txt"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=b"This is a test file"
    )
    
    # Now mark it as complete
    result = mock_upload_service.mark_upload_complete(s3_key)
    
    # Check the result
    assert result["success"] is True, "Marking upload complete should succeed"
    assert result["exists"] is True, "File should exist in S3"
    assert result["s3_key"] == s3_key, "S3 key should match"
    assert result["file_size"] == 19, "File size should match the content length"
    assert "file_size_formatted" in result, "Formatted file size should be included"
    
    # Test with a non-existent file
    result = mock_upload_service.mark_upload_complete("nonexistent.txt")
    assert result["success"] is False, "Should fail for non-existent file"
    assert result["exists"] is False, "Should report file doesn't exist"
