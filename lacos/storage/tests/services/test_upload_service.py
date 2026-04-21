import tempfile
import shutil
import pytest
import boto3
from moto import mock_aws
import requests
import os
import json
from io import BytesIO
from urllib.parse import urlparse


from lacos.storage.services.upload_service import UploadService

# Use a static bucket name for testing
TEST_BUCKET_NAME = 'test-bucket'
TEST_FOLDER_NAME = 'test-folder'

# Global variables to store test results
_init_result = None
_parts_result = None

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
def mock_upload_service(mock_s3):
    """Create an UploadService instance with mock settings"""
    service = UploadService(skip_bucket_check=True)
    # Override the bucket names for testing
    service.ingest_bucket = TEST_BUCKET_NAME
    service.production_bucket = TEST_BUCKET_NAME
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    return service

def test_generate_presigned_post(mock_upload_service):
    """Test generating a presigned post URL for a single file"""
    # Test with large file (should trigger multipart)
    large_file_size = 6 * 1024 * 1024 * 1024  # 6GB
    result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        file_size=large_file_size
    )

    # Check the result for multipart upload
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["file_name"] == "test.txt", "File name should be preserved"
    assert result["s3_key"] == "test.txt", "S3 key should match the filename when no prefix"
    assert result["upload_type"] == "multipart", "Upload type should be multipart for large files"
    assert "upload_id" in result, "Result should include upload_id for multipart"
    assert "parts_info" in result, "Result should include parts_info for multipart"
    assert "expires_in" in result, "Result should include expiration time"
    
    # Test with small file (should use single upload)
    small_file_size = 10 * 1024 * 1024  # 10MB
    single_result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        file_size=small_file_size
    )
    
    # Check the result for single-part upload
    assert single_result["success"] is True, "Presigned URL generation should succeed"
    assert single_result["file_name"] == "test.txt", "File name should be preserved"
    assert single_result["s3_key"] == "test.txt", "S3 key should match the filename when no prefix"
    assert single_result["upload_type"] == "single", "Upload type should be single when multipart is disabled"
    assert "presigned_post" in single_result, "Result should include presigned_post data"
    assert "url" in single_result["presigned_post"], "Result should include the presigned URL"
    assert "fields" in single_result["presigned_post"], "Result should include form fields"
    
    # Check the URL format for single-part upload
    assert single_result["presigned_post"]["url"].startswith("http://"), "URL should be properly formatted"
    
    # Check that the fields contain the necessary S3 form fields for single-part upload
    fields = single_result["presigned_post"]["fields"]
    assert "Content-Type" in fields, "Fields should include Content-Type"
    assert fields["Content-Type"] == "text/plain", "Content-Type should match input"
    assert "key" in fields, "Fields should include the object key"
    assert fields["key"] == "test.txt", "Key should match the S3 key"

def test_generate_presigned_post_with_path_prefix(mock_upload_service):
    """Test generating a presigned post URL with a path prefix"""
    # Test with multipart upload (default)
    result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        path_prefix="folder/subfolder"
    )
    
    # Check the result
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["s3_key"] == "folder/subfolder/test.txt", "S3 key should include the path prefix"
    assert result["upload_type"] == "multipart", "Upload type should be multipart by default"
    
    # Test with single-part upload
    single_result = mock_upload_service.generate_presigned_post(
        file_name="test.txt",
        file_type="text/plain",
        path_prefix="folder/subfolder",
        file_size=10 * 1024 * 1024  # 10MB, below threshold
    )
    
    assert single_result["success"] is True, "Presigned URL generation should succeed"
    assert single_result["s3_key"] == "folder/subfolder/test.txt", "S3 key should include the path prefix"
    assert single_result["upload_type"] == "single", "Upload type should be single when multipart is disabled"

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
        {"file_name": "file1.txt", "file_type": "text/plain", "file_size": 6 * 1024 * 1024 * 1024},  # 6GB
        {"file_name": "file2.txt", "file_type": "text/plain", "file_size": 6 * 1024 * 1024 * 1024},  # 6GB
        {"file_name": "file3.jpg", "file_type": "image/jpeg", "file_size": 6 * 1024 * 1024 * 1024}   # 6GB
    ]

    # Test with large files (should trigger multipart)
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
        assert presigned_post["upload_type"] == "multipart", f"Item {i} should use multipart upload for large files"
        assert "upload_id" in presigned_post, f"Item {i} should include upload_id"
        assert "parts_info" in presigned_post, f"Item {i} should include parts_info for multipart"
    
    # Test with small files (should use single upload)
    small_files_metadata = [
        {"file_name": "small1.txt", "file_type": "text/plain", "file_size": 10 * 1024 * 1024},  # 10MB
        {"file_name": "small2.txt", "file_type": "text/plain", "file_size": 10 * 1024 * 1024},  # 10MB
        {"file_name": "small3.jpg", "file_type": "image/jpeg", "file_size": 10 * 1024 * 1024}   # 10MB
    ]
    single_result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=small_files_metadata,
        path_prefix=TEST_FOLDER_NAME
    )
    
    # Check the overall result for single-part
    assert single_result["success"] is True, "Batch presigned URL generation should succeed"
    assert single_result["total_urls"] == 3, "Should generate 3 presigned URLs"
    
    # Check individual URLs for single-part
    for i, presigned_post in enumerate(single_result["presigned_posts"]):
        file_meta = small_files_metadata[i]
        assert presigned_post["file_name"] == file_meta["file_name"], f"File name should match for item {i}"
        assert presigned_post["s3_key"] == f"{TEST_FOLDER_NAME}/{file_meta['file_name']}", f"S3 key should include folder for item {i}"
        assert presigned_post["upload_type"] == "single", f"Item {i} should use single-part upload for small files"
        assert "presigned_post" in presigned_post, f"Item {i} should include presigned_post data"
        assert "url" in presigned_post["presigned_post"], f"Item {i} should include URL in presigned_post"
        assert "fields" in presigned_post["presigned_post"], f"Item {i} should include fields in presigned_post"

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
    result = mock_upload_service.generate_presigned_post(
        file_name="",
        file_type="text/plain"
    )

    assert result["success"] is False
    assert "File name cannot be empty" in result["error"]

    result = mock_upload_service.generate_presigned_post(
        file_name="nested/path.txt",
        file_type="text/plain",
    )
    assert result["success"] is False
    assert "path separators" in result["error"]


def test_generate_presigned_post_blocks_active_content_types(mock_upload_service):
    result = mock_upload_service.generate_presigned_post(
        file_name="dangerous.html",
        file_type="text/html",
        file_size=1024,
    )

    assert result["success"] is False
    assert "not allowed" in result["error"]


def test_generate_batch_presigned_posts_rejects_traversal_paths(mock_upload_service):
    result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=[
            {"file_name": "file.txt", "file_type": "text/plain", "path": "../escape"},
        ],
        path_prefix=TEST_FOLDER_NAME,
        file_size=1024,
    )

    assert result["success"] is False
    assert result["total_failures"] == 1


def test_generate_presigned_post_does_not_log_sensitive_policy_fields(mock_upload_service, caplog):
    with caplog.at_level("INFO"):
        result = mock_upload_service.generate_presigned_post(
            file_name="test.txt",
            file_type="text/plain",
            file_size=10 * 1024 * 1024,
        )

    assert result["success"] is True
    assert "Generated presigned URL" not in caplog.text
    assert "Generated presigned fields" not in caplog.text

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


def test_mark_upload_complete_rejects_blocked_content_type(mock_s3, mock_upload_service):
    s3_key = f"{TEST_FOLDER_NAME}/dangerous.html"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=b"<html></html>",
        ContentType="text/html",
    )

    result = mock_upload_service.mark_upload_complete(s3_key)

    assert result["success"] is False
    assert result["exists"] is True
    assert "not allowed" in result["error"]

def test_presigned_url_actual_upload(mock_s3, mock_upload_service):
    """Test that we can actually upload a file using the presigned URL"""
    # Generate a presigned post URL with single-part upload
    file_name = "test_upload.txt"
    file_content = b"This is a test of the presigned URL upload"
    
    result = mock_upload_service.generate_presigned_post(
        file_name=file_name,
        file_type="text/plain",
        path_prefix=TEST_FOLDER_NAME,
        file_size=10 * 1024 * 1024  # 10MB, below threshold  # Use single-part for this test
    )
    
    # Verify we got a valid presigned URL
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert result["upload_type"] == "single", "Upload type should be single"
    assert "presigned_post" in result, "Result should include the presigned post data"
    assert "url" in result["presigned_post"], "Result should include the presigned URL"
    assert "fields" in result["presigned_post"], "Result should include the form fields"
    
    s3_key = result["s3_key"]
    
    # For moto mock environment, we need to directly upload to simulate the presigned URL behavior
    # In a real environment, we would use the presigned URL with a regular HTTP client
    # But for the test, we'll just upload directly
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=file_content,
        ContentType="text/plain"
    )
    
    # Now verify the file was uploaded correctly
    response = mock_s3.get_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key
    )
    
    # Check the uploaded content
    uploaded_content = response['Body'].read()
    assert uploaded_content == file_content, "Uploaded content should match original content"
    
    # Use mark_upload_complete to verify the upload
    verify_result = mock_upload_service.mark_upload_complete(s3_key)
    assert verify_result["success"] is True, "Verification should succeed"
    assert verify_result["exists"] is True, "File should exist in S3"
    assert verify_result["file_size"] == len(file_content), "File size should match"

def test_browser_upload_simulation(mock_s3, mock_upload_service):
    """
    Test that simulates how a browser would use the presigned URLs.
    
    This is a more realistic test of the presigned URL flow, mocking
    the HTTP requests a browser would make to upload a file directly to S3.
    """
    # Generate presigned URLs for a batch of files with single-part upload
    files_metadata = [
        {"file_name": "browser_test1.txt", "file_type": "text/plain", "path": "browser_uploads"}
    ]
    
    batch_result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=files_metadata,
        path_prefix=TEST_FOLDER_NAME,
        file_size=10 * 1024 * 1024  # 10MB, below threshold  # Use single-part for this test
    )
    
    assert batch_result["success"] is True, "Batch presigned URL generation should succeed"
    assert batch_result["total_urls"] == 1, "Should generate 1 presigned URL"
    
    # Get the first presigned post data
    presigned_data = batch_result["presigned_posts"][0]
    s3_key = presigned_data["s3_key"]
    assert presigned_data["upload_type"] == "single", "Upload type should be single"
    
    # In a real browser, this would be done with an HTML form or fetch API
    # For testing, we'll simulate by directly putting the object
    file_content = b"This is a browser upload test"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=file_content,
        ContentType="text/plain"
    )
    
    # Now verify with mark_upload_complete
    verify_result = mock_upload_service.mark_upload_complete(s3_key)
    assert verify_result["success"] is True, "Verification should succeed"
    assert verify_result["exists"] is True, "File should exist in S3"
    assert verify_result["file_size"] == len(file_content), "File size should match"

# ----- Multipart Upload Tests -----

def test_initialize_multipart_upload(mock_upload_service):
    """Test initializing a multipart upload"""
    file_name = "large_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "multipart_test"
    
    result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix
    )
    
    # Check the result
    assert result["success"] is True, "Multipart upload initialization should succeed"
    assert "upload_id" in result, "Result should include an upload ID"
    assert result["file_name"] == file_name, "File name should be preserved"
    assert result["s3_key"] == f"{path_prefix}/{file_name}", "S3 key should include path prefix"
    assert result["file_type"] == file_type, "File type should be preserved"
    
    # Store the result in a global variable for other tests to use
    global _init_result
    _init_result = result

def test_get_upload_part_urls(mock_upload_service):
    """Test generating presigned URLs for multipart upload parts"""
    # First initialize a multipart upload if not already done
    global _init_result
    if _init_result is None:
        test_initialize_multipart_upload(mock_upload_service)
    
    # Now get presigned URLs for parts
    part_count = 3
    result = mock_upload_service.get_upload_part_urls(
        s3_key=_init_result["s3_key"],
        upload_id=_init_result["upload_id"],
        part_count=part_count
    )
    
    # Check the result
    assert result["success"] is True, "Getting part upload URLs should succeed"
    assert len(result["presigned_urls"]) == part_count, f"Should generate {part_count} presigned URLs"
    assert result["s3_key"] == _init_result["s3_key"], "S3 key should match the initialization"
    assert result["upload_id"] == _init_result["upload_id"], "Upload ID should match the initialization"
    
    # Check each URL
    for i, part_url in enumerate(result["presigned_urls"]):
        assert "part_number" in part_url, "Each URL should include a part number"
        assert part_url["part_number"] == i + 1, "Part numbers should be sequential"
        assert "url" in part_url, "Each URL entry should include the actual URL"
        assert isinstance(part_url["url"], str), "URL should be a string"
        
        # Check if the URL contains the right parameters
        assert "partNumber=" in part_url["url"], "URL should include part number parameter"
        assert "uploadId=" in part_url["url"], "URL should include upload ID parameter"
    
    # Store the results for other tests
    global _parts_result
    _parts_result = result

def test_multipart_upload_uses_target_bucket(mock_s3, mock_upload_service):
    """Ensure multipart uploads honor the provided bucket name."""
    target_bucket = "alternate-bucket"
    mock_s3.create_bucket(Bucket=target_bucket)

    file_name = "bucket_target_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "bucket_target"

    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix,
        bucket_name=target_bucket,
    )
    assert init_result["success"] is True, "Multipart upload initialization should succeed"
    assert init_result["bucket_name"] == target_bucket, "Initialization should keep the target bucket"

    s3_key = init_result["s3_key"]
    upload_id = init_result["upload_id"]

    part_count = 2
    urls_result = mock_upload_service.get_upload_part_urls(
        s3_key=s3_key,
        upload_id=upload_id,
        part_count=part_count,
        bucket_name=target_bucket,
    )
    assert urls_result["success"] is True, "Part URL generation should succeed"
    assert urls_result["bucket_name"] == target_bucket, "Part URLs should reflect the target bucket"

    parts = []
    part_size = 5 * 1024 * 1024
    for part in urls_result["presigned_urls"]:
        response = mock_s3.upload_part(
            Bucket=target_bucket,
            Key=s3_key,
            UploadId=upload_id,
            PartNumber=part["part_number"],
            Body=b"X" * part_size,
        )
        parts.append({"part_number": part["part_number"], "etag": response["ETag"]})

    complete_result = mock_upload_service.complete_multipart_upload(
        s3_key=s3_key,
        upload_id=upload_id,
        parts=parts,
        bucket_name=target_bucket,
    )
    assert complete_result["success"] is True, "Multipart completion should succeed"
    assert complete_result["bucket"] == target_bucket, "Completion should use the target bucket"
    mock_s3.head_object(Bucket=target_bucket, Key=s3_key)

def test_complete_multipart_upload(mock_s3, mock_upload_service):
    """Test completing a multipart upload"""
    # Instead of relying on global variables, initialize a new multipart upload directly in this test
    file_name = "test_complete_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "complete_test"
    s3_key = f"{path_prefix}/{file_name}"
    
    # Initialize the multipart upload
    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix
    )
    
    assert init_result["success"] is True, "Multipart upload initialization should succeed"
    upload_id = init_result["upload_id"]
    
    # Get presigned URLs for parts
    part_count = 3
    urls_result = mock_upload_service.get_upload_part_urls(
        s3_key=s3_key,
        upload_id=upload_id,
        part_count=part_count
    )
    
    assert urls_result["success"] is True, "Getting part upload URLs should succeed"
    
    # Simulate uploading parts
    parts = []
    # Use 5MB part size to meet S3 minimum requirements
    part_size = 5 * 1024 * 1024  # 5MB
    
    for i, part_url in enumerate(urls_result["presigned_urls"]):
        part_number = part_url["part_number"]
        # Create unique content for each part
        part_content = b"X" * part_size
        
        # In a real-world scenario, we would use the presigned URL to upload
        # For testing with moto, we need to use the S3 client directly
        response = mock_s3.upload_part(
            Bucket=TEST_BUCKET_NAME,
            Key=s3_key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=part_content
        )
        
        # Collect the ETags for the complete multipart request
        parts.append({
            "part_number": part_number,
            "etag": response["ETag"]
        })
    
    # Complete the multipart upload
    result = mock_upload_service.complete_multipart_upload(
        s3_key=s3_key,
        upload_id=upload_id,
        parts=parts
    )
    
    # Check the result
    assert result["success"] is True, "Completing multipart upload should succeed"
    assert result["s3_key"] == s3_key, "S3 key should match"
    assert "etag" in result, "Result should include an ETag"
    assert "file_size" in result, "Result should include the file size"
    assert "file_size_formatted" in result, "Result should include the formatted file size"

def test_abort_multipart_upload(mock_s3, mock_upload_service):
    """Test aborting a multipart upload"""
    # Initialize a new multipart upload directly in this test instead of relying on global variables
    file_name = "abort_test_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "abort_test"
    s3_key = f"{path_prefix}/{file_name}"
    
    # Initialize the multipart upload
    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix
    )
    
    assert init_result["success"] is True, "Multipart upload initialization should succeed"
    upload_id = init_result["upload_id"]
    
    # Abort the multipart upload
    result = mock_upload_service.abort_multipart_upload(
        s3_key=s3_key,
        upload_id=upload_id
    )
    
    # Check the result
    assert result["success"] is True, "Aborting multipart upload should succeed"
    assert result["s3_key"] == s3_key, "S3 key should match"
    assert result["upload_id"] == upload_id, "Upload ID should match"
    
    # Verify the upload was aborted by trying to list parts (should fail)
    try:
        mock_upload_service.s3_client.list_parts(
            Bucket=TEST_BUCKET_NAME,
            Key=s3_key,
            UploadId=upload_id
        )
        pytest.fail("list_parts should fail after abort")
    except Exception as e:
        # This is expected - the multipart upload should no longer exist
        assert "NoSuchUpload" in str(e) or "does not exist" in str(e), "Should fail with NoSuchUpload error"

def test_list_multipart_uploads(mock_s3, mock_upload_service):
    """Test listing in-progress multipart uploads"""
    # Initialize a few multipart uploads
    uploads = []
    for i in range(3):
        result = mock_upload_service.initialize_multipart_upload(
            file_name=f"multipart_file_{i}.dat",
            file_type="application/octet-stream",
            path_prefix="list_test"
        )
        uploads.append(result)
    
    # List the multipart uploads
    result = mock_upload_service.list_multipart_uploads()
    
    # Check the result
    assert result["success"] is True, "Listing multipart uploads should succeed"
    assert "uploads" in result, "Result should include a list of uploads"
    assert "count" in result, "Result should include a count of uploads"
    
    # Check if all our uploads are in the list
    assert result["count"] >= len(uploads), "All uploads should be listed"
    
    # Verify the uploads exist in the list
    upload_ids = set(upload["upload_id"] for upload in result["uploads"])
    for upload in uploads:
        assert upload["upload_id"] in upload_ids, "Each initialized upload should be listed"
    
    # Clean up the uploads
    for upload in uploads:
        mock_upload_service.abort_multipart_upload(
            s3_key=upload["s3_key"],
            upload_id=upload["upload_id"]
        )

def test_multipart_upload_large_file_simulation(mock_s3, mock_upload_service):
    """
    Test a full multipart upload flow with a simulated large file.
    
    This test simulates the typical flow of a multipart upload:
    1. Initialize the multipart upload
    2. Split the file into parts and upload each part
    3. Complete the multipart upload
    4. Verify the result
    """
    # Setup
    file_name = "simulated_large_file.dat"
    file_type = "application/octet-stream"
    path_prefix = "simulation_test"
    s3_key = f"{path_prefix}/{file_name}"
    
    # Create a simulated large file (3 parts, 5MB each to meet S3 minimum requirements)
    # Increase part size to ensure we meet the minimum size requirements
    part_size = 6 * 1024 * 1024  # 6MB per part
    part_count = 3
    
    # Step 1: Initialize the multipart upload
    init_result = mock_upload_service.initialize_multipart_upload(
        file_name=file_name,
        file_type=file_type,
        path_prefix=path_prefix
    )
    
    assert init_result["success"] is True, "Multipart upload initialization should succeed"
    upload_id = init_result["upload_id"]
    
    # Step 2: Get presigned URLs for each part
    urls_result = mock_upload_service.get_upload_part_urls(
        s3_key=s3_key,
        upload_id=upload_id,
        part_count=part_count
    )
    
    assert urls_result["success"] is True, "Getting part upload URLs should succeed"
    
    # Step 3: Upload each part
    parts = []
    for part_url in urls_result["presigned_urls"]:
        part_number = part_url["part_number"]
        # Create a fixed-size content for each part to ensure we meet minimum size requirements
        # Use a simple byte pattern that can be efficiently created
        content = b'X' * part_size
        
        # Upload the part directly with the S3 client (in a real scenario, the presigned URL would be used)
        response = mock_s3.upload_part(
            Bucket=TEST_BUCKET_NAME,
            Key=s3_key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=content
        )
        
        parts.append({
            "part_number": part_number,
            "etag": response["ETag"]
        })
    
    # Step 4: Complete the multipart upload
    complete_result = mock_upload_service.complete_multipart_upload(
        s3_key=s3_key,
        upload_id=upload_id,
        parts=parts
    )
    
    assert complete_result["success"] is True, "Completing multipart upload should succeed"
    
    # Step 5: Verify the file was uploaded correctly
    # Verify with mark_upload_complete
    verify_result = mock_upload_service.mark_upload_complete(s3_key)
    assert verify_result["success"] is True, "Verification should succeed"
    assert verify_result["exists"] is True, "File should exist in S3"
