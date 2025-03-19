import unittest
from unittest.mock import Mock, patch, MagicMock
import io
import boto3
from botocore.exceptions import ClientError

from ..services.upload_service import UploadService


class MockFile:
    """Mock file object for testing purposes."""
    
    def __init__(self, name, content=b"test content", size=None):
        self.name = name
        self.content = content
        self.size = size or len(content)
        self._file = io.BytesIO(content)
    
    def read(self):
        return self.content
    
    def seek(self, position):
        self._file.seek(position)


class TestUploadService(unittest.TestCase):
    """Test cases for UploadService."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create a mock for S3 client
        self.mock_s3_client = Mock()
        
        # Patch the boto3 client creation to return our mock
        self.patcher = patch('boto3.client', return_value=self.mock_s3_client)
        self.mock_boto3_client = self.patcher.start()
        
        # Create UploadService instance
        self.upload_service = UploadService()
        
        # Override S3 client with our mock
        self.upload_service.s3_client = self.mock_s3_client
        
        # Mock bucket existence check to always return True
        self.upload_service.ensure_bucket_exists = Mock(return_value=True)
    
    def tearDown(self):
        """Clean up after each test."""
        self.patcher.stop()
    
    def test_configure_transfer(self):
        """Test that transfer configuration is created correctly."""
        config = self.upload_service._configure_transfer()
        
        # Check if the config has expected attributes
        self.assertEqual(config.multipart_threshold, 8 * 1024 * 1024)  # 8 MB
        self.assertEqual(config.max_concurrency, 5)
        self.assertEqual(config.multipart_chunksize, 8 * 1024 * 1024)
        self.assertTrue(config.use_threads)
    
    def test_upload_single_file_success(self):
        """Test successful single file upload."""
        # Prepare test data
        file = MockFile("test.txt", b"test content")
        file_name = file.name
        file_size = file.size
        bucket_name = "test-bucket"
        relative_path = "folder/test.txt"
        
        # Configure the mock to simulate successful upload
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service._upload_single_file(
            file, file_name, file_size, bucket_name, relative_path, 
            self.upload_service._configure_transfer()
        )
        
        # Verify the result
        self.assertTrue(result["success"])
        self.assertEqual(result["name"], file_name)
        self.assertEqual(result["s3_key"], relative_path)
        self.assertEqual(result["size"], file_size)
        
        # Verify the mock was called correctly
        self.mock_s3_client.upload_fileobj.assert_called_once()
    
    def test_upload_single_file_failure(self):
        """Test handling of failed single file upload."""
        # Prepare test data
        file = MockFile("test.txt", b"test content")
        file_name = file.name
        file_size = file.size
        bucket_name = "test-bucket"
        relative_path = "folder/test.txt"
        
        # Configure the mock to simulate a failure
        error_message = "Test error"
        self.mock_s3_client.upload_fileobj.side_effect = Exception(error_message)
        
        # Call the method
        result = self.upload_service._upload_single_file(
            file, file_name, file_size, bucket_name, relative_path, 
            self.upload_service._configure_transfer()
        )
        
        # Verify the result
        self.assertFalse(result["success"])
        self.assertEqual(result["name"], file_name)
        self.assertEqual(result["error"], error_message)
    
    def test_process_file_paths(self):
        """Test the processing of file paths to handle duplicate filenames."""
        # Prepare test data with duplicate filenames in different paths
        file_paths = {
            "file1.txt": "folder1/file1.txt",
            "file2.txt": "folder2/file2.txt",
            "duplicate.txt": "folder1/duplicate.txt",
            "duplicate.txt_2": "folder2/duplicate.txt"  # In real case, frontend would add suffix
        }
        
        # Call the method
        result = self.upload_service._process_file_paths(file_paths)
        
        # Verify the result - paths should be unique keys
        self.assertEqual(len(result), 4)
        self.assertEqual(result["folder1/file1.txt"], "file1.txt")
        self.assertEqual(result["folder2/file2.txt"], "file2.txt")
        self.assertEqual(result["folder1/duplicate.txt"], "duplicate.txt")
        self.assertEqual(result["folder2/duplicate.txt"], "duplicate.txt_2")
    
    def test_upload_files_directly_with_same_filename_different_paths(self):
        """Test uploading files with the same filename in different paths."""
        # Create mock files with the same name
        file1 = MockFile("acl.json", b"content1")
        file2 = MockFile("acl.json_2", b"content2")  # In real case, frontend would add suffix
        files = [file1, file2]
        
        # Create file paths mapping - using paths as keys and filenames as values
        file_paths = {
            "zaghawa/zag_eoi_20141009_1/acl.json": "acl.json",
            "zaghawa/zag_eoi_20141016_1/acl.json": "acl.json_2"
        }
        
        # Configure the mocks
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method directly
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertEqual(len(result["uploaded_files"]), 2)
        self.assertEqual(len(result["failed_files"]), 0)
        
        # Verify both files were uploaded to their correct paths
        upload_calls = self.mock_s3_client.upload_fileobj.call_args_list
        self.assertEqual(len(upload_calls), 2)
        
        # Extract the paths from the upload calls
        uploaded_paths = [call[0][2] for call in upload_calls]
        self.assertIn("zaghawa/zag_eoi_20141009_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_1/acl.json", uploaded_paths)
    
    def test_upload_multiple_files_with_identical_names(self):
        """Test uploading multiple files with identical names in different directories."""
        # Create multiple files with the same name
        file1 = MockFile("acl.json", b"content1")  # First acl.json
        file2 = MockFile("acl.json_2", b"content2")  # Second acl.json
        file3 = MockFile("acl.json_3", b"content3")  # Third acl.json
        file4 = MockFile("0=ocfl_object_1.0", b"content4")  # Different file name for variety
        files = [file1, file2, file3, file4]
        
        # Create file paths mapping with multiple files having the same basename but in different paths
        file_paths = {
            "zaghawa/zag_eoi_20141009_1/acl.json": "acl.json",
            "zaghawa/zag_eoi_20141016_1/acl.json": "acl.json_2",
            "zaghawa/zag_eoi_20141016_2/acl.json": "acl.json_3",
            "zaghawa/zag_eoi_20141009_1/0=ocfl_object_1.0": "0=ocfl_object_1.0"
        }
        
        # Configure the mocks
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertTrue(result["success"])
        self.assertEqual(len(result["uploaded_files"]), 4)
        self.assertEqual(len(result["failed_files"]), 0)
        
        # Verify all files were uploaded to their correct paths
        upload_calls = self.mock_s3_client.upload_fileobj.call_args_list
        self.assertEqual(len(upload_calls), 4)
        
        # Extract the paths from the upload calls
        uploaded_paths = [call[0][2] for call in upload_calls]
        
        # Verify each path was uploaded
        self.assertIn("zaghawa/zag_eoi_20141009_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_2/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141009_1/0=ocfl_object_1.0", uploaded_paths)
    
    def test_upload_with_filename_path_format(self):
        """Test uploading files with the filename->path format instead of path->filename."""
        # Create files
        file1 = MockFile("doc.txt", b"content1")
        file2 = MockFile("image.jpg", b"content2")
        files = [file1, file2]
        
        # Create file paths mapping in filename->path format (the way frontend would typically send it)
        file_paths = {
            "doc.txt": "folder1/doc.txt",
            "image.jpg": "folder2/image.jpg"
        }
        
        # Configure the mocks
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertTrue(result["success"])
        self.assertEqual(len(result["uploaded_files"]), 2)
        self.assertEqual(len(result["failed_files"]), 0)
        
        # Verify all files were uploaded to their correct paths
        upload_calls = self.mock_s3_client.upload_fileobj.call_args_list
        self.assertEqual(len(upload_calls), 2)
        
        # Extract the paths from the upload calls
        uploaded_paths = [call[0][2] for call in upload_calls]
        self.assertIn("folder1/doc.txt", uploaded_paths)
        self.assertIn("folder2/image.jpg", uploaded_paths)
    
    def test_upload_files_with_missing_path_information(self):
        """Test handling of files without path information."""
        # Create mock files
        file1 = MockFile("with_path.txt", b"content1")
        file2 = MockFile("without_path.txt", b"content2")
        files = [file1, file2]
        
        # Only provide path for one file - use path->filename format
        file_paths = {
            "folder/with_path.txt": "with_path.txt"
        }
        
        # Configure the mock
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertFalse(result["success"])  # Overall success should be False
        self.assertEqual(len(result["uploaded_files"]), 1)
        self.assertEqual(len(result["failed_files"]), 1)
        
        # Verify only one file was uploaded
        self.mock_s3_client.upload_fileobj.assert_called_once()
        
        # Verify the failed file has the expected error
        self.assertEqual(result["failed_files"][0]["name"], "without_path.txt")
        self.assertEqual(result["failed_files"][0]["error"], "Missing path information")
    
    def test_upload_files_with_valid_and_invalid_files(self):
        """Test a mix of valid uploads and errors."""
        # Create mock files
        file1 = MockFile("valid.txt", b"content1")
        file2 = MockFile("error.txt", b"content2")
        files = [file1, file2]
        
        # Provide paths for both files - using path->filename format
        file_paths = {
            "folder/valid.txt": "valid.txt",
            "folder/error.txt": "error.txt"
        }
        
        # Configure the mock to succeed for first file and fail for second
        def upload_file_side_effect(*args, **kwargs):
            if args[2] == "folder/error.txt":
                raise Exception("Test error")
            return None
        
        self.mock_s3_client.upload_fileobj.side_effect = upload_file_side_effect
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertFalse(result["success"])  # Overall success should be False
        self.assertEqual(len(result["uploaded_files"]), 1)
        self.assertEqual(len(result["failed_files"]), 1)
        
        # Verify the uploaded file info
        self.assertEqual(result["uploaded_files"][0]["name"], "valid.txt")
        
        # Verify the failed file info
        self.assertEqual(result["failed_files"][0]["name"], "error.txt")
        self.assertEqual(result["failed_files"][0]["error"], "Test error")
        
        # Specifically check there are no duplicate entries in the failed files list
        failed_file_names = [f["name"] for f in result["failed_files"]]
        self.assertEqual(failed_file_names, ["error.txt"])
    
    def test_empty_files_list(self):
        """Test handling of empty files list."""
        result = self.upload_service.upload_files_directly(
            [], "testfolder", "test-bucket", {}
        )
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "No files provided for upload")
    
    def test_empty_folder_name(self):
        """Test handling of empty folder name."""
        result = self.upload_service.upload_files_directly(
            [MockFile("test.txt")], "", "test-bucket", {}
        )
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "No folder name provided for upload")
    
    def test_bucket_creation_failure(self):
        """Test handling of bucket creation failure."""
        # Override ensure_bucket_exists to return False
        self.upload_service.ensure_bucket_exists = Mock(return_value=False)
        
        result = self.upload_service.upload_files_directly(
            [MockFile("test.txt")], "testfolder", "test-bucket", {"folder/test.txt": "test.txt"}
        )
        
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Failed to ensure bucket exists: test-bucket")
    
    def test_upload_duplicate_files_to_different_paths(self):
        """
        Test uploading the same file to multiple different paths.
        
        This tests a common scenario where the same file (like acl.json) needs to be
        uploaded to multiple different directories. This requires being able to use
        the same file object more than once without getting 'seek of closed file' errors.
        """
        # Create a single file that will be used multiple times
        file1 = MockFile("acl.json", b"test content")
        files = [file1]
        
        # Create file paths mapping to use this file in multiple locations
        file_paths = {
            "zaghawa/zag_eoi_20141009_1/acl.json": "acl.json",
            "zaghawa/zag_eoi_20141016_1/acl.json": "acl.json",  # Same file, different path
            "zaghawa/zag_eoi_20141016_2/acl.json": "acl.json"   # Same file, different path
        }
        
        # Configure the mock
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertTrue(result["success"])
        # We expect 3 successful uploads of the same file to different paths
        self.assertEqual(len(result["uploaded_files"]), 3)
        self.assertEqual(len(result["failed_files"]), 0)
        
        # Verify all paths were uploaded
        upload_calls = self.mock_s3_client.upload_fileobj.call_args_list
        self.assertEqual(len(upload_calls), 3)
        
        # Extract the paths from the upload calls
        uploaded_paths = [call[0][2] for call in upload_calls]
        self.assertIn("zaghawa/zag_eoi_20141009_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_2/acl.json", uploaded_paths)
    
    def test_realistic_upload_with_duplicate_filenames(self):
        """
        Test a more realistic scenario with duplicate filenames that Django would rename.
        
        This simulates what actually happens with Django request.FILES when
        multiple files with the same name are uploaded from different directories.
        Django will add suffixes like '_2' to disambiguate them.
        """
        # Create files with Django-style naming for duplicates (adding _2, _3 suffixes)
        file1 = MockFile("acl.json", b"content1")  # Original name was acl.json 
        file2 = MockFile("acl.json_2", b"content2")  # Original name was also acl.json
        file3 = MockFile("acl.json_3", b"content3")  # Original name was also acl.json
        file4 = MockFile("0=ocfl_object_1.0", b"content4")  # Unique name
        file5 = MockFile("0=ocfl_object_1.0_2", b"content5")  # Original name was 0=ocfl_object_1.0
        files = [file1, file2, file3, file4, file5]
        
        # Map paths to the Django-renamed files (not the original names)
        # This is what would happen after our view processes the uploads
        file_paths = {
            "zaghawa/zag_eoi_20141009_1/acl.json": "acl.json",  # Django named it acl.json
            "zaghawa/zag_eoi_20141016_1/acl.json": "acl.json_2",  # Django renamed to acl.json_2
            "zaghawa/zag_eoi_20141016_2/acl.json": "acl.json_3",  # Django renamed to acl.json_3
            "zaghawa/zag_eoi_20141009_1/0=ocfl_object_1.0": "0=ocfl_object_1.0",
            "zaghawa/zag_eoi_20141016_1/0=ocfl_object_1.0": "0=ocfl_object_1.0_2"
        }
        
        # Configure the mock
        self.mock_s3_client.upload_fileobj.return_value = None
        
        # Call the method
        result = self.upload_service.upload_files_directly(
            files, "testfolder", "test-bucket", file_paths
        )
        
        # Verify the result
        self.assertTrue(result["success"])
        self.assertEqual(len(result["uploaded_files"]), 5)
        self.assertEqual(len(result["failed_files"]), 0)
        
        # Verify all paths were uploaded
        upload_calls = self.mock_s3_client.upload_fileobj.call_args_list
        self.assertEqual(len(upload_calls), 5)
        
        # Extract the paths from the upload calls
        uploaded_paths = [call[0][2] for call in upload_calls]
        self.assertIn("zaghawa/zag_eoi_20141009_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_1/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_2/acl.json", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141009_1/0=ocfl_object_1.0", uploaded_paths)
        self.assertIn("zaghawa/zag_eoi_20141016_1/0=ocfl_object_1.0", uploaded_paths)


if __name__ == "__main__":
    unittest.main()
