import pytest
from unittest.mock import MagicMock

from lacos.storage.services.collection_service import CollectionService, BucketListingPage

# Import constants from test_constants.py
from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

# We can use mock_s3 and temp_dir fixtures from conftest.py
# Only define fixtures that aren't in conftest.py

@pytest.fixture
def mock_collection_service(mock_s3):
    """Create a CollectionService instance with mock settings"""
    CollectionService._instance = None
    service = CollectionService(skip_bucket_check=True)
    # Override the bucket names for testing
    service.ingest_bucket = TEST_INGEST_BUCKET
    service.production_bucket = TEST_PRODUCTION_BUCKET
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    yield service
    CollectionService._instance = None


def test_bucket_listing_page_behaves_like_sequence():
    page = BucketListingPage(
        items=[{"name": "alpha"}, {"name": "beta"}],
        has_more=True,
        next_token="token-1",
        bucket="bucket",
        prefix="",
    )
    assert len(page) == 2
    assert page[0]["name"] == "alpha"
    assert [item["name"] for item in page] == ["alpha", "beta"]
    assert page.has_more is True
    assert page.next_token == "token-1"

def test_is_collection_path(mock_collection_service):
    """Test the is_collection_path method"""
    # Should identify collection paths
    assert mock_collection_service.is_collection_path("algerien/algerien")
    assert mock_collection_service.is_collection_path("test/test/")
    assert mock_collection_service.is_collection_path("a/b/c/c")
    
    # Should not identify non-collection paths
    assert not mock_collection_service.is_collection_path("algerien")
    assert not mock_collection_service.is_collection_path("algerien/bundle")
    assert not mock_collection_service.is_collection_path("a/b/c/d")

def test_is_collection_path_enhanced(mock_collection_service):
    """Test the enhanced is_collection_path method"""
    # Simple collection paths
    assert mock_collection_service.is_collection_path("zaghawa/zaghawa")
    assert mock_collection_service.is_collection_path("test/test/")
    
    # Nested collection paths
    assert mock_collection_service.is_collection_path("zaghawa/zaghawa/v1/content")
    assert mock_collection_service.is_collection_path("test/test/v1/")
    assert mock_collection_service.is_collection_path("a/a/v2/content")
    
    # Should not identify non-collection paths
    assert not mock_collection_service.is_collection_path("zaghawa")
    assert not mock_collection_service.is_collection_path("zaghawa/bundle")
    assert not mock_collection_service.is_collection_path("zaghawa/bundle/v1/content")
    assert not mock_collection_service.is_collection_path("a/b/c/d")

def test_get_collection_parent_path(mock_collection_service):
    """Test the get_collection_parent_path method"""
    # Simple collection case
    assert mock_collection_service.get_collection_parent_path("algerien/algerien") == "algerien"
    
    # Nested paths
    assert mock_collection_service.get_collection_parent_path("test/test/v1/content") == "test"
    assert mock_collection_service.get_collection_parent_path("zaghawa/zaghawa/v1") == "zaghawa"
    
    # Non-collection paths should still return parent
    assert mock_collection_service.get_collection_parent_path("a/b/c") == "a/b"

def setup_ocfl_objects(mock_s3):
    """Set up OCFL objects in the test bucket"""
    # Create OCFL marker files
    ocfl_keys = [
        "collection1/0=ocfl_object_1.0",
        "collection1/subcollection/0=ocfl_object_1.0",
        "collection2/bundle1/0=ocfl_object_1.0"
    ]
    
    for key in ocfl_keys:
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=key,
            Body="ocfl_object_1.0"
        )

def test_is_ocfl_object(mock_s3, mock_collection_service):
    """Test the is_ocfl_object method"""
    setup_ocfl_objects(mock_s3)
    
    # Test with paths that have OCFL markers
    assert mock_collection_service.is_ocfl_object(TEST_BUCKET_NAME, "collection1")
    assert mock_collection_service.is_ocfl_object(TEST_BUCKET_NAME, "collection1/subcollection")
    assert mock_collection_service.is_ocfl_object(TEST_BUCKET_NAME, "collection2/bundle1")
    
    # Test with paths that don't have OCFL markers
    assert not mock_collection_service.is_ocfl_object(TEST_BUCKET_NAME, "collection2")
    assert not mock_collection_service.is_ocfl_object(TEST_BUCKET_NAME, "nonexistent")

def test_find_ocfl_objects(mock_s3, mock_collection_service):
    """Test the find_ocfl_objects method"""
    setup_ocfl_objects(mock_s3)
    
    # Find all OCFL objects
    ocfl_objects = mock_collection_service.find_ocfl_objects(TEST_BUCKET_NAME)
    
    # Verify results
    assert sorted(ocfl_objects) == sorted(["collection1", "collection1/subcollection", "collection2/bundle1"])
    
    # Test with prefix to narrow search
    ocfl_objects = mock_collection_service.find_ocfl_objects(TEST_BUCKET_NAME, "collection1")
    assert sorted(ocfl_objects) == sorted(["collection1", "collection1/subcollection"])

def setup_bucket_contents(mock_s3):
    """Set up a directory structure in the test bucket"""
    content_keys = [
        # Collection files
        "collection/collection/file1.txt",
        "collection/collection/0=ocfl_object_1.0",
        "collection/collection/acl.json",
        
        # Bundle files
        "collection/bundle1/file2.txt",
        "collection/bundle1/0=ocfl_object_1.0",
        
        # Nested structure
        "nested/nested/v1/content/file3.txt",
        "nested/nested/0=ocfl_object_1.0",
        "nested/bundle2/v1/content/file4.txt"
    ]
    
    # Directory markers
    dir_keys = [
        "collection/",
        "collection/collection/",
        "collection/bundle1/",
        "nested/",
        "nested/nested/",
        "nested/nested/v1/",
        "nested/nested/v1/content/",
        "nested/bundle2/",
        "nested/bundle2/v1/",
        "nested/bundle2/v1/content/"
    ]
    
    # Upload files
    for key in content_keys:
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=key,
            Body=f"Content of {key}"
        )
    
    # Create directory markers
    for key in dir_keys:
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=key,
            Body=""
        )

def test_list_bucket_contents(mock_s3, mock_collection_service):
    """Test the list_bucket_contents method"""
    setup_bucket_contents(mock_s3)
    
    # List root contents
    contents = mock_collection_service.list_bucket_contents(TEST_BUCKET_NAME)
    assert isinstance(contents, BucketListingPage)
    assert contents.has_more is False
    
    # Verify results - should have directories
    dirs = [item for item in contents if item.get("is_dir", False)]
    assert len(dirs) == 2, f"Expected 2 directories, got {len(dirs)}"
    dir_names = {d["name"] for d in dirs}
    assert "collection" in dir_names
    assert "nested" in dir_names
    
    # List collection contents
    contents = mock_collection_service.list_bucket_contents(TEST_BUCKET_NAME, "collection")
    assert isinstance(contents, BucketListingPage)
    assert contents.has_more is False
    
    # Verify directories
    dirs = [item for item in contents if item.get("is_dir", False)]
    assert len(dirs) == 2, f"Expected 2 directories, got {len(dirs)}"
    dir_names = {d["name"] for d in dirs}
    assert "collection" in dir_names
    assert "bundle1" in dir_names
    
    # List collection files
    contents = mock_collection_service.list_bucket_contents(TEST_BUCKET_NAME, "collection/collection")
    assert isinstance(contents, BucketListingPage)
    assert contents.has_more is False
    
    # Verify files
    files = [item for item in contents if not item.get("is_dir", False)]
    assert len(files) == 3, f"Expected 3 files, got {len(files)}"
    file_names = {f["name"] for f in files}
    assert "file1.txt" in file_names
    assert "0=ocfl_object_1.0" in file_names
    assert "acl.json" in file_names


def test_list_bucket_contents_pagination(mock_s3, mock_collection_service):
    """list_bucket_contents should honour max_keys and continuation tokens."""
    setup_bucket_contents(mock_s3)

    first_page = mock_collection_service.list_bucket_contents(
        TEST_BUCKET_NAME,
        max_keys=1,
    )
    assert isinstance(first_page, BucketListingPage)
    assert len(first_page) == 1
    assert first_page.has_more is True
    assert first_page.next_token is not None

    second_page = mock_collection_service.list_bucket_contents(
        TEST_BUCKET_NAME,
        max_keys=1,
        continuation_token=first_page.next_token,
    )
    assert isinstance(second_page, BucketListingPage)
    assert len(second_page) == 1
    assert second_page.next_token != first_page.next_token


def test_list_bucket_contents_raises_on_error_when_requested(mock_collection_service):
    """Errors should bubble up when raise_errors=True."""
    mock_collection_service.s3_client.list_objects_v2 = MagicMock(
        side_effect=Exception("Invalid continuation token")
    )

    with pytest.raises(Exception, match="Invalid continuation token"):
        mock_collection_service.list_bucket_contents(
            TEST_BUCKET_NAME,
            max_keys=1,
            continuation_token="token",
            raise_errors=True,
        )


def test_list_bucket_contents_returns_empty_page_on_error_by_default(mock_collection_service):
    """Default behavior should remain non-raising for callers that expect a safe fallback."""
    mock_collection_service.s3_client.list_objects_v2 = MagicMock(
        side_effect=Exception("Invalid continuation token")
    )

    page = mock_collection_service.list_bucket_contents(
        TEST_BUCKET_NAME,
        max_keys=1,
        continuation_token="token",
    )

    assert isinstance(page, BucketListingPage)
    assert len(page) == 0
    assert page.has_more is False
    assert page.next_token is None

def test_get_folder_structure(mock_s3, mock_collection_service):
    """Test the get_folder_structure method"""
    setup_bucket_contents(mock_s3)
    
    # Get the structure for a specific collection
    structure = mock_collection_service.get_folder_structure(TEST_BUCKET_NAME, "collection")
    
    # Verify the structure
    assert structure["type"] == "folder"
    assert structure["name"] == "collection"
    assert len(structure["children"]) == 2
    
    # Check the children are correctly identified as folders
    child_names = {child["name"] for child in structure["children"]}
    assert "collection" in child_names
    assert "bundle1" in child_names
    
    # Verify nested structure
    for child in structure["children"]:
        if child["name"] == "collection":
            # The collection subfolder should have files
            assert child["type"] == "folder"
            assert len(child["children"]) == 3
            file_names = {c["name"] for c in child["children"]}
            assert "file1.txt" in file_names
            assert "0=ocfl_object_1.0" in file_names
            assert "acl.json" in file_names 
