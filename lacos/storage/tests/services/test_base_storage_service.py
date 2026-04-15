import os
import pytest
from botocore.exceptions import ClientError

# Import constants from test_constants.py
from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

# We don't need to redefine fixtures as they're imported from conftest.py

def test_ensure_bucket_exists(mock_s3, mock_base_service):
    """Test ensure_bucket_exists method"""
    # Test with existing bucket
    result = mock_base_service.ensure_bucket_exists(TEST_BUCKET_NAME)
    assert result is True, "Failed to recognize existing bucket"
    
    # Test with non-existing bucket (should create it)
    new_bucket = "new-test-bucket"
    result = mock_base_service.ensure_bucket_exists(new_bucket)
    assert result is True, "Failed to create new bucket"
    
    # Verify the bucket was created
    response = mock_s3.list_buckets()
    bucket_names = [bucket['Name'] for bucket in response['Buckets']]
    assert new_bucket in bucket_names, "New bucket was not created"

def test_format_size(mock_base_service):
    """Test the _format_size utility method"""
    # Test various sizes
    assert mock_base_service._format_size(500) == "500.00 B"
    assert mock_base_service._format_size(1024) == "1.00 KB"
    assert mock_base_service._format_size(1024 * 1024) == "1.00 MB"
    assert mock_base_service._format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert mock_base_service._format_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"

def test_get_file_content(mock_s3, mock_base_service, temp_dir):
    """Test get_file_content method"""
    # Create a test file and upload it
    test_file_path = os.path.join(temp_dir, "test.txt")
    test_content = b"This is a test file."
    with open(test_file_path, "wb") as f:
        f.write(test_content)
    
    # Upload the file
    s3_key = "test/test.txt"
    mock_s3.upload_file(test_file_path, TEST_BUCKET_NAME, s3_key)
    
    # Test getting the file content
    content_result = mock_base_service.get_file_content(TEST_BUCKET_NAME, s3_key)
    assert "content" in content_result, "File content not returned"
    assert content_result["content"] == test_content, "File content does not match"
    assert content_result["metadata"]["content_length"] == len(test_content), "Content length does not match"
    assert content_result["bucket_type"] in ["ingest", "production"], "Invalid bucket type"

def test_delete_object(mock_s3, mock_base_service, temp_dir):
    """Test delete_object method"""
    # Create and upload a test file
    test_file_path = os.path.join(temp_dir, "delete_test.txt")
    with open(test_file_path, "w") as f:
        f.write("This is a test file to delete.")
    
    # Upload the file
    s3_key = "test/delete_test.txt"
    mock_s3.upload_file(test_file_path, TEST_BUCKET_NAME, s3_key)
    
    # Verify the file exists
    response = mock_s3.list_objects_v2(Bucket=TEST_BUCKET_NAME, Prefix=s3_key)
    assert "Contents" in response, "Test file was not uploaded"
    
    # Delete the file
    delete_result = mock_base_service.delete_object(TEST_BUCKET_NAME, s3_key)
    assert delete_result["success"] is True, "Delete operation failed"
    
    # Verify the file is deleted
    response = mock_s3.list_objects_v2(Bucket=TEST_BUCKET_NAME, Prefix=s3_key)
    assert "Contents" not in response, "File was not deleted"

def test_delete_directory(mock_s3, mock_base_service, temp_dir):
    """Test delete_object method with is_directory=True"""
    # Create and upload multiple files to create a directory structure
    prefix = "test_dir/"
    for i in range(3):
        test_file_path = os.path.join(temp_dir, f"file{i}.txt")
        with open(test_file_path, "w") as f:
            f.write(f"This is test file {i}.")
        mock_s3.upload_file(test_file_path, TEST_BUCKET_NAME, f"{prefix}file{i}.txt")
    
    # Verify files exist
    response = mock_s3.list_objects_v2(Bucket=TEST_BUCKET_NAME, Prefix=prefix)
    assert "Contents" in response, "Test files were not uploaded"
    assert len(response["Contents"]) == 3, "Not all test files were uploaded"
    
    # Delete the directory
    delete_result = mock_base_service.delete_object(TEST_BUCKET_NAME, prefix, is_directory=True)
    assert delete_result["success"] is True, "Delete directory operation failed"
    assert delete_result["deleted_objects"] == 3, "Not all files were deleted"
    
    # Verify the directory is deleted
    response = mock_s3.list_objects_v2(Bucket=TEST_BUCKET_NAME, Prefix=prefix)
    assert "Contents" not in response, "Directory was not deleted"