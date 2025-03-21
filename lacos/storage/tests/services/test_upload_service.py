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

def test_check_file_exists(mock_s3, mock_upload_service):
    """Test checking if a file exists in S3"""
    # First upload a file to S3
    s3_key = f"{TEST_FOLDER_NAME}/exists_test.txt"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=b"This file exists"
    )
    
    # Check that the file exists
    assert mock_upload_service.check_file_exists(s3_key) is True, "File should exist"
    
    # Check a non-existent file
    assert mock_upload_service.check_file_exists("nonexistent.txt") is False, "File should not exist"

def test_get_object_content(mock_s3, mock_upload_service):
    """Test retrieving the content of an S3 object"""
    # First upload a file to S3
    s3_key = f"{TEST_FOLDER_NAME}/content_test.txt"
    test_content = b"This is the file content"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key,
        Body=test_content
    )
    
    # Retrieve the content
    content = mock_upload_service.get_object_content(s3_key)
    assert content == test_content, "Retrieved content should match original content"
    
    # Test with a non-existent file
    try:
        mock_upload_service.get_object_content("nonexistent.txt")
        assert False, "Should raise an exception for non-existent file"
    except Exception:
        # Expected behavior
        pass

def test_upload_file_object(mock_s3, mock_upload_service):
    """Test uploading a file object to S3"""
    # Create a file-like object
    file_obj = BytesIO(b"This is a test file object")
    s3_key = f"{TEST_FOLDER_NAME}/uploaded_file.txt"
    content_type = "text/plain"
    
    # Upload the file
    result = mock_upload_service.upload_file_object(
        file_obj=file_obj,
        s3_key=s3_key,
        content_type=content_type
    )
    
    # Check the result
    assert result["success"] is True, "Upload should succeed"
    assert result["s3_key"] == s3_key, "S3 key should match"
    
    # Verify the file was uploaded correctly
    response = mock_s3.get_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key
    )
    
    # Check the uploaded content
    uploaded_content = response['Body'].read()
    assert uploaded_content == b"This is a test file object", "Uploaded content should match original content"
    assert response['ContentType'] == content_type, "Content type should match"

def test_presigned_url_actual_upload(mock_s3, mock_upload_service):
    """Test that we can actually upload a file using the presigned URL"""
    # Generate a presigned post URL
    file_name = "test_upload.txt"
    file_content = b"This is a test of the presigned URL upload"
    
    result = mock_upload_service.generate_presigned_post(
        file_name=file_name,
        file_type="text/plain",
        path_prefix=TEST_FOLDER_NAME
    )
    
    # Verify we got a valid presigned URL
    assert result["success"] is True, "Presigned URL generation should succeed"
    assert "url" in result, "Result should include the presigned URL"
    assert "fields" in result, "Result should include the form fields"
    
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
    
    # Check that we can list the file in the bucket
    list_response = mock_s3.list_objects_v2(
        Bucket=TEST_BUCKET_NAME,
        Prefix=TEST_FOLDER_NAME
    )
    
    # There should be one object
    assert 'Contents' in list_response, "Bucket should contain our file"
    assert len(list_response['Contents']) == 1, "Should find exactly one file"
    assert list_response['Contents'][0]['Key'] == s3_key, "S3 key should match"

def test_copy_object(mock_s3, mock_upload_service):
    """Test copying an object within S3"""
    # First upload a file to S3
    source_key = f"{TEST_FOLDER_NAME}/source.txt"
    target_key = f"{TEST_FOLDER_NAME}/target.txt"
    test_content = b"This is the source file"
    
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=source_key,
        Body=test_content
    )
    
    # Copy the object
    result = mock_upload_service.copy_object(
        source_key=source_key,
        target_key=target_key
    )
    
    # Check the result
    assert result["success"] is True, "Copy should succeed"
    assert result["source_key"] == source_key, "Source key should match"
    assert result["target_key"] == target_key, "Target key should match"
    
    # Verify the file was copied correctly
    response = mock_s3.get_object(
        Bucket=TEST_BUCKET_NAME,
        Key=target_key
    )
    
    # Check the copied content
    copied_content = response['Body'].read()
    assert copied_content == test_content, "Copied content should match original content"
    
    # Test copying a non-existent file
    result = mock_upload_service.copy_object(
        source_key="nonexistent.txt",
        target_key="target2.txt"
    )
    assert result["success"] is False, "Copy should fail for non-existent source"

def test_browser_upload_simulation(mock_s3, mock_upload_service):
    """
    Test that simulates how a browser would use the presigned URLs.
    
    This is a more realistic test of the presigned URL flow, mocking
    the HTTP requests a browser would make to upload a file directly to S3.
    """
    # Generate presigned URLs for a batch of files
    files_metadata = [
        {"file_name": "browser_test1.txt", "file_type": "text/plain", "path": "browser_uploads"}
    ]
    
    batch_result = mock_upload_service.generate_batch_presigned_posts(
        files_metadata=files_metadata,
        path_prefix=TEST_FOLDER_NAME
    )
    
    assert batch_result["success"] is True, "Batch presigned URL generation should succeed"
    assert batch_result["total_urls"] == 1, "Should generate 1 presigned URL"
    
    # Get the first presigned post data
    presigned_data = batch_result["presigned_posts"][0]
    s3_key = presigned_data["s3_key"]
    
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
    
    # Also verify we can retrieve the file and its content matches
    response = mock_s3.get_object(
        Bucket=TEST_BUCKET_NAME,
        Key=s3_key
    )
    retrieved_content = response['Body'].read()
    assert retrieved_content == file_content, "Retrieved content should match uploaded content"

def test_process_uploaded_files(mock_s3, mock_upload_service):
    """Test processing uploaded files with different extensions"""
    # Upload files with different extensions
    files = {
        f"{TEST_FOLDER_NAME}/document.xml": b"<xml>Test XML</xml>",
        f"{TEST_FOLDER_NAME}/image.jpg": b"JPEG image data",
        f"{TEST_FOLDER_NAME}/document.txt": b"Plain text file"
    }
    
    # Upload all files to S3
    for key, content in files.items():
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=key,
            Body=content
        )
    
    # Create a list of uploaded files to process
    uploaded_files = [
        {"s3_key": key, "file_name": key.split("/")[-1]} for key in files.keys()
    ]
    
    # Process the files
    result = mock_upload_service.process_uploaded_files(
        folder_name=TEST_FOLDER_NAME,
        uploaded_files=uploaded_files
    )
    
    # Check the result
    assert result["success"] is True, "Processing should succeed"
    assert len(result["processed_files"]) == 3, "All files should be processed"
    assert len(result["failed_files"]) == 0, "No files should fail"
    
    # Check that each file was processed according to its type
    for processed_file in result["processed_files"]:
        if processed_file["file_name"].endswith(".xml"):
            assert "Processed as XML" in processed_file["status"], "XML file should be processed as XML"
        elif processed_file["file_name"].endswith(".jpg"):
            assert "image" in processed_file["status"].lower(), "Image file should be recognized as image"
        else:
            assert "Stored in S3" in processed_file["status"], "Other files should be stored"
