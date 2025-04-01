import pytest
import os
import boto3
from moto import mock_aws
from dotenv import load_dotenv
from pathlib import Path

from lacos.storage.services.file_discovery_service import FileDiscoveryService

# Load environment variables from .django file
env_file_path = os.path.join('/app', '.envs/.local/.django')
load_dotenv(env_file_path)

# Test bucket names
TEST_BUCKET_NAME = 'test-bucket'


# Test to verify environment variables are loaded
def test_env_vars_loaded():
    """Verify that environment variables from .django are loaded correctly."""
    # Check specific environment variables for base patterns
    assert os.environ.get('COLLECTION_PATH_PATTERN') == '{collection_id}/{collection_id}'
    assert os.environ.get('BUNDLE_PATH_PATTERN') == '{collection_id}/{bundle_id}'
    
    # The derived patterns should either be explicitly set or will be derived
    # If set explicitly, check their values
    # If not set, that's also fine as they'll be derived in the code
    if 'RESOURCE_PATH_PATTERN' in os.environ:
        assert os.environ.get('RESOURCE_PATH_PATTERN') == '{collection_id}/{bundle_id}/v1/content/Resources/{resource_filename}'
    
    if 'COLLECTION_XML_PATH' in os.environ:
        # Check if explicitly set
        collection_xml = os.environ.get('COLLECTION_XML_PATH')
        assert collection_xml is None or collection_xml == '{collection_id}/{collection_id}/v1/content/{collection_id}.xml'
    
    if 'BUNDLE_XML_PATH' in os.environ:
        # Check if explicitly set
        bundle_xml = os.environ.get('BUNDLE_XML_PATH')
        assert bundle_xml is None or bundle_xml == '{collection_id}/{bundle_id}/v1/content/{bundle_id}.xml'
    
    print(f"Environment variables loaded: {dict((k,v) for k,v in os.environ.items() if k.endswith('_PATH') or k.endswith('_PATTERN'))}")


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
def discovery_service(mock_s3):
    """Create a FileDiscoveryService with mock S3 client"""
    service = FileDiscoveryService()
    # Override the bucket names for testing
    service.production_bucket = TEST_BUCKET_NAME
    service.ingest_bucket = TEST_BUCKET_NAME
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    
    # Debug print the path structure
    print(f"Service path structure: {service.path_structure}")
    
    return service


# Test path pattern formatting
def test_collection_path(discovery_service):
    path = discovery_service.form_collection_path("algerien")
    assert path == "algerien/algerien"

def test_bundle_path(discovery_service):
    path = discovery_service.form_bundle_path("algerien", "bundle123")
    assert path == "algerien/bundle123"

def test_resource_path(discovery_service):
    path = discovery_service.form_resource_path("algerien", "bundle123", "audio.mp3")
    assert path == "algerien/bundle123/v1/content/Resources/audio.mp3"

def test_collection_xml_path(discovery_service):
    path = discovery_service.form_collection_xml_path("algerien")
    assert path == "algerien/algerien/v1/content/algerien.xml"

def test_bundle_xml_path(discovery_service):
    path = discovery_service.form_bundle_xml_path("algerien", "bundle123")
    assert path == "algerien/bundle123/v1/content/bundle123.xml"


# Test S3 operations with real folder structure
def test_find_collections_s3(mock_s3, discovery_service):
    """Test finding collections using the S3 API with a real directory structure"""
    # Create test collection folders with proper structure
    for collection_id in ["algerien", "alwateti"]:
        # Create collection XML file
        xml_path = f"{collection_id}/{collection_id}/v1/content/{collection_id}.xml"
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=xml_path,
            Body=f"<xml>Collection {collection_id}</xml>"
        )
    
    # Also create a folder that's not a collection
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="not_collection/file.txt",
        Body="This is not a collection"
    )
    
    # Call the method
    collections = discovery_service.find_collections_s3(bucket=TEST_BUCKET_NAME)
    
    # Check results
    assert len(collections) == 2
    assert "algerien" in collections
    assert "alwateti" in collections


def test_find_bundles_in_collection_s3(mock_s3, discovery_service):
    """Test finding bundles in a collection using the S3 API"""
    collection_id = "algerien"
    
    # Create collection XML
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{collection_id}/{collection_id}/v1/content/{collection_id}.xml",
        Body=f"<xml>Collection {collection_id}</xml>"
    )
    
    # Create test bundle folders with proper structure
    for bundle_id in ["bundle1", "bundle2"]:
        # Create bundle XML file
        xml_path = f"{collection_id}/{bundle_id}/v1/content/{bundle_id}.xml"
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=xml_path,
            Body=f"<xml>Bundle {bundle_id}</xml>"
        )
    
    # Create a folder that's not a proper bundle
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{collection_id}/not_bundle/file.txt",
        Body="This is not a bundle"
    )
    
    # Call the method
    bundles = discovery_service.find_bundles_in_collection_s3(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id
    )
    
    # Check results
    assert len(bundles) == 2
    assert "bundle1" in bundles
    assert "bundle2" in bundles
    assert "not_bundle" not in bundles


def test_find_resources_in_bundle_s3(mock_s3, discovery_service):
    """Test finding resources in a bundle using the S3 API"""
    collection_id = "algerien"
    bundle_id = "bundle1"
    
    # Create bundle XML
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{collection_id}/{bundle_id}/v1/content/{bundle_id}.xml",
        Body=f"<xml>Bundle {bundle_id}</xml>"
    )
    
    # Create test resources
    resources_prefix = f"{collection_id}/{bundle_id}/v1/content/Resources/"
    test_resources = ["audio1.mp3", "audio2.mp3", "metadata.json"]
    
    for resource in test_resources:
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=f"{resources_prefix}{resource}",
            Body=f"Content of {resource}"
        )
    
    # Call the method
    resources = discovery_service.find_resources_in_bundle_s3(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id,
        bundle_id=bundle_id
    )
    
    # Check results
    assert len(resources) == 3
    for resource in test_resources:
        assert resource in resources


def test_find_collection_and_bundle_xmls_s3(mock_s3, discovery_service):
    """Test finding both collection and bundle XML files using the S3 API"""
    # Create test collections and bundles
    collections = ["algerien", "alwateti"]
    bundles_by_collection = {
        "algerien": ["bundle1", "bundle2"],
        "alwateti": ["bundle3"]
    }
    
    # Create the structure in S3
    for collection_id in collections:
        # Create collection XML
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=f"{collection_id}/{collection_id}/v1/content/{collection_id}.xml",
            Body=f"<xml>Collection {collection_id}</xml>"
        )
        
        # Create bundles for this collection
        for bundle_id in bundles_by_collection.get(collection_id, []):
            mock_s3.put_object(
                Bucket=TEST_BUCKET_NAME,
                Key=f"{collection_id}/{bundle_id}/v1/content/{bundle_id}.xml",
                Body=f"<xml>Bundle {bundle_id}</xml>"
            )
    
    # Call the method
    result = discovery_service.find_collection_and_bundle_xmls_s3(TEST_BUCKET_NAME)
    
    # Check results
    assert len(result['potential_collection_xmls']) == 2
    assert "algerien/algerien/v1/content/algerien.xml" in result['potential_collection_xmls']
    assert "alwateti/alwateti/v1/content/alwateti.xml" in result['potential_collection_xmls']
    
    assert len(result['potential_bundle_xmls']) == 3
    assert "algerien/bundle1/v1/content/bundle1.xml" in result['potential_bundle_xmls']
    assert "algerien/bundle2/v1/content/bundle2.xml" in result['potential_bundle_xmls']
    assert "alwateti/bundle3/v1/content/bundle3.xml" in result['potential_bundle_xmls']


def test_get_collection_xml(mock_s3, discovery_service):
    """Test retrieving a collection XML file"""
    collection_id = "algerien"
    xml_content = b"<xml>Collection content</xml>"
    
    # Create the collection XML in S3
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{collection_id}/{collection_id}/v1/content/{collection_id}.xml",
        Body=xml_content
    )
    
    # Get the XML content
    result = discovery_service.get_collection_xml(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id
    )
    
    # Check the result
    assert result == xml_content


def test_get_bundle_xml(mock_s3, discovery_service):
    """Test retrieving a bundle XML file"""
    collection_id = "algerien"
    bundle_id = "bundle1"
    xml_content = b"<xml>Bundle content</xml>"
    
    # Create the bundle XML in S3
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{collection_id}/{bundle_id}/v1/content/{bundle_id}.xml",
        Body=xml_content
    )
    
    # Get the XML content
    result = discovery_service.get_bundle_xml(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id,
        bundle_id=bundle_id
    )
    
    # Check the result
    assert result == xml_content


def test_get_resource(mock_s3, discovery_service):
    """Test retrieving a resource file"""
    collection_id = "algerien"
    bundle_id = "bundle1"
    resource_filename = "audio.mp3"
    resource_content = b"Binary audio content"
    
    # Create the resource in S3
    resource_key = f"{collection_id}/{bundle_id}/v1/content/Resources/{resource_filename}"
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=resource_key,
        Body=resource_content
    )
    
    # Get the resource content
    result = discovery_service.get_resource(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id,
        bundle_id=bundle_id,
        resource_filename=resource_filename
    )
    
    # Check the result
    assert result == resource_content


def test_get_missing_resource(mock_s3, discovery_service):
    """Test retrieving a resource that doesn't exist"""
    collection_id = "algerien"
    bundle_id = "bundle1"
    resource_filename = "missing.mp3"
    
    # Get the missing resource
    result = discovery_service.get_resource(
        bucket=TEST_BUCKET_NAME,
        collection_id=collection_id,
        bundle_id=bundle_id,
        resource_filename=resource_filename
    )
    
    # Check that the result is None
    assert result is None
