import os
import shutil
import tempfile
import pytest
import json
import boto3
from pathlib import Path
from moto import mock_aws
from django.test import TestCase
from django.conf import settings

from lacos.storage.management.commands.standardize_ocfl_structure import (
    is_collection, PathHandler, Command
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests and clean it up afterwards"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_s3_bucket():
    """Create a mock S3 bucket for testing"""
    with mock_aws():
        s3 = boto3.client('s3')
        bucket_name = 'test-bucket'
        s3.create_bucket(Bucket=bucket_name)
        yield bucket_name


@pytest.fixture
def mock_collection_dir(temp_dir):
    """Create a mock collection directory structure"""
    # Setup directory structure
    # /temp_dir/collection_name/collection_name
    collection_name = "algerien"
    parent_dir = Path(temp_dir) / collection_name
    collection_dir = parent_dir / collection_name
    os.makedirs(collection_dir / "v1" / "content", exist_ok=True)
    
    # Create OCFL version marker
    with open(collection_dir / "0=ocfl_object_1.0", "w") as f:
        f.write("ocfl_object_1.0")
    
    # Create ACL file
    with open(collection_dir / "acl.json", "w") as f:
        json.dump({"permissions": []}, f)
    
    # Create XML file
    with open(collection_dir / "v1" / "content" / f"{collection_name}.xml", "w") as f:
        f.write("<collection>Test Collection</collection>")
    
    return collection_dir


@pytest.fixture
def mock_s3_collection(mock_s3_bucket):
    """Create a mock collection in S3"""
    s3 = boto3.client('s3')
    collection_name = "algerien"
    base_path = f"{collection_name}/{collection_name}"
    
    # Create OCFL version marker
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/0=ocfl_object_1.0",
        Body="ocfl_object_1.0"
    )
    
    # Create ACL file
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/acl.json",
        Body=json.dumps({"permissions": []})
    )
    
    # Create XML file
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/v1/content/{collection_name}.xml",
        Body="<collection>Test Collection</collection>"
    )
    
    return f"s3://{mock_s3_bucket}/{base_path}"


@pytest.fixture
def mock_bundle_dir(temp_dir):
    """Create a mock bundle directory structure"""
    # Setup directory structure
    # /temp_dir/collection_name/bundle_name
    collection_name = "algerien"
    bundle_name = "alwateti_nonstructured_1"
    parent_dir = Path(temp_dir) / collection_name
    bundle_dir = parent_dir / bundle_name
    
    # Create directory structure
    content_dir = bundle_dir / "v1" / "content"
    resources_dir = content_dir / "Resources"
    os.makedirs(resources_dir, exist_ok=True)
    
    # Create OCFL version marker
    with open(bundle_dir / "0=ocfl_object_1.0", "w") as f:
        f.write("ocfl_object_1.0")
    
    # Create ACL file
    with open(bundle_dir / "acl.json", "w") as f:
        json.dump({"permissions": []}, f)
    
    # Create XML file
    with open(content_dir / f"{bundle_name}.xml", "w") as f:
        f.write("<bundle>Test Bundle</bundle>")
    
    # Create sample resource files
    with open(resources_dir / "test_file1.wav", "w") as f:
        f.write("test audio content")
    
    with open(resources_dir / "test_file2.wav", "w") as f:
        f.write("more test audio content")
    
    return bundle_dir


@pytest.fixture
def mock_s3_bundle(mock_s3_bucket):
    """Create a mock bundle in S3"""
    s3 = boto3.client('s3')
    collection_name = "algerien"
    bundle_name = "alwateti_nonstructured_1"
    base_path = f"{collection_name}/{bundle_name}"
    
    # Create OCFL version marker
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/0=ocfl_object_1.0",
        Body="ocfl_object_1.0"
    )
    
    # Create ACL file
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/acl.json",
        Body=json.dumps({"permissions": []})
    )
    
    # Create XML file
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/v1/content/{bundle_name}.xml",
        Body="<bundle>Test Bundle</bundle>"
    )
    
    # Create sample resource files
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/v1/content/Resources/test_file1.wav",
        Body="test audio content"
    )
    s3.put_object(
        Bucket=mock_s3_bucket,
        Key=f"{base_path}/v1/content/Resources/test_file2.wav",
        Body="more test audio content"
    )
    
    return f"s3://{mock_s3_bucket}/{base_path}"


def test_is_collection_detection_local(mock_collection_dir, mock_bundle_dir):
    """Test that is_collection correctly identifies local collections and bundles"""
    # Test collection detection
    assert is_collection(mock_collection_dir), "Failed to identify collection directory"
    # Test bundle detection
    assert not is_collection(mock_bundle_dir), "Failed to identify bundle directory"


def test_is_collection_detection_s3(mock_s3_collection, mock_s3_bundle):
    """Test that is_collection correctly identifies S3 collections and bundles"""
    # Test collection detection
    assert is_collection(mock_s3_collection), "Failed to identify S3 collection"
    # Test bundle detection
    assert not is_collection(mock_s3_bundle), "Failed to identify S3 bundle"


def test_transform_collection_local(mock_collection_dir):
    """Test transforming a local collection structure"""
    # Transform the collection
    command = Command()
    success = command.transform_structure(mock_collection_dir)
    assert success, "Transform failed for collection"
    
    # Verify the new structure
    content_dir = mock_collection_dir / 'v1' / 'content'
    metadata_dir = content_dir / 'metadata'
    
    # Check metadata directory exists
    assert metadata_dir.exists(), "Metadata directory was not created"
    
    # Check XML files were moved to metadata
    xml_files = list(metadata_dir.glob('*.xml'))
    assert len(xml_files) > 0, "No XML files found in metadata directory"
    
    # Check acl.json was moved if it exists
    acl_file = mock_collection_dir / 'acl.json'
    if acl_file.exists():
        assert (metadata_dir / 'acl.json').exists(), "acl.json was not moved to metadata directory"


def test_transform_collection_s3(mock_s3_collection):
    """Test transforming an S3 collection structure"""
    # Transform the collection
    command = Command()
    success = command.transform_structure(mock_s3_collection)
    assert success, "Transform failed for S3 collection"
    
    # Verify the new structure using PathHandler
    path_handler = PathHandler(mock_s3_collection)
    content_path = f"{mock_s3_collection}/v1/content"
    metadata_path = f"{content_path}/metadata"
    
    # Check metadata directory exists (by checking if any files exist in it)
    metadata_handler = PathHandler(metadata_path)
    assert metadata_handler.is_dir(), "Metadata directory was not created"
    
    # Check XML files were moved to metadata
    xml_files = metadata_handler.glob('*.xml')
    assert len(list(xml_files)) > 0, "No XML files found in metadata directory"
    
    # Check acl.json was moved
    acl_path = f"{metadata_path}/acl.json"
    acl_handler = PathHandler(acl_path)
    assert acl_handler.exists(), "acl.json was not moved to metadata directory"


def test_transform_bundle_local(mock_bundle_dir):
    """Test transforming a local bundle structure"""
    # Transform the bundle
    command = Command()
    success = command.transform_structure(mock_bundle_dir)
    assert success, "Transform failed for bundle"
    
    # Verify the new structure
    content_dir = mock_bundle_dir / 'v1' / 'content'
    metadata_dir = content_dir / 'metadata'
    data_dir = content_dir / 'data'
    
    # Check metadata directory exists
    assert metadata_dir.exists(), "Metadata directory was not created"
    
    # Check Resources was renamed to data
    assert data_dir.exists(), "Resources directory was not renamed to data"
    assert not (content_dir / 'Resources').exists(), "Resources directory still exists after rename"
    
    # Check XML files were moved to metadata
    xml_files = list(metadata_dir.glob('*.xml'))
    assert len(xml_files) > 0, "No XML files found in metadata directory"
    
    # Check acl.json was moved
    assert (metadata_dir / 'acl.json').exists(), "acl.json was not moved to metadata directory"


def test_transform_bundle_s3(mock_s3_bundle):
    """Test transforming an S3 bundle structure"""
    # Transform the bundle
    command = Command()
    success = command.transform_structure(mock_s3_bundle)
    assert success, "Transform failed for S3 bundle"
    
    # Verify the new structure using PathHandler
    content_path = f"{mock_s3_bundle}/v1/content"
    metadata_path = f"{content_path}/metadata"
    data_path = f"{content_path}/data"
    
    # Check metadata directory exists
    metadata_handler = PathHandler(metadata_path)
    assert metadata_handler.is_dir(), "Metadata directory was not created"
    
    # Check Resources was renamed to data
    data_handler = PathHandler(data_path)
    assert data_handler.is_dir(), "Resources directory was not renamed to data"
    
    resources_handler = PathHandler(f"{content_path}/Resources")
    assert not resources_handler.exists(), "Resources directory still exists after rename"
    
    # Check XML files were moved to metadata
    xml_files = metadata_handler.glob('*.xml')
    assert len(list(xml_files)) > 0, "No XML files found in metadata directory"
    
    # Check acl.json was moved
    acl_handler = PathHandler(f"{metadata_path}/acl.json")
    assert acl_handler.exists(), "acl.json was not moved to metadata directory"


def test_transform_already_transformed_local(mock_bundle_dir):
    """Test transforming an already transformed local structure"""
    command = Command()
    # First transform
    command.transform_structure(mock_bundle_dir)
    
    # Then try to transform again
    result = command.transform_structure(mock_bundle_dir)
    
    # Should still return True
    assert result, "Transform should return True even when already transformed"
    
    # Structure should remain correct
    content_dir = mock_bundle_dir / 'v1' / 'content'
    metadata_dir = content_dir / 'metadata'
    data_dir = content_dir / 'data'
    
    assert metadata_dir.exists(), "Metadata directory should still exist"
    assert data_dir.exists(), "Data directory should still exist"
    
    xml_files = list(metadata_dir.glob('*.xml'))
    assert len(xml_files) > 0, "XML files should still be in metadata"
    
    assert any(data_dir.iterdir()), "Data directory should not be empty"


def test_transform_already_transformed_s3(mock_s3_bundle):
    """Test transforming an already transformed S3 structure"""
    command = Command()
    # First transform
    command.transform_structure(mock_s3_bundle)
    # Then try to transform again
    result = command.transform_structure(mock_s3_bundle)
    
    # Should still return True
    assert result, "Transform should return True even when already transformed"
    
    # Structure should remain correct using PathHandler
    content_path = f"{mock_s3_bundle}/v1/content"
    metadata_path = f"{content_path}/metadata"
    data_path = f"{content_path}/data"
    
    metadata_handler = PathHandler(metadata_path)
    data_handler = PathHandler(data_path)
    
    assert metadata_handler.is_dir(), "Metadata directory should still exist"
    assert data_handler.is_dir(), "Data directory should still exist"
    
    xml_files = metadata_handler.glob('*.xml')
    assert len(list(xml_files)) > 0, "XML files should still be in metadata"
    
    # Check data directory has content
    assert len(list(data_handler.glob('*'))) > 0, "Data directory should not be empty"
