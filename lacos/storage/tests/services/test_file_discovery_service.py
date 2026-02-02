import pytest
import os
from dotenv import load_dotenv
from pathlib import Path

from lacos.storage.services.file_discovery_service import FileDiscoveryService

# Import constants from test_constants.py
from .test_constants import TEST_BUCKET_NAME, TEST_INGEST_BUCKET, TEST_PRODUCTION_BUCKET

# Load environment variables from .django file
env_file_path = os.path.join('/app', '.envs/.local/.django')
load_dotenv(env_file_path)

# Test to verify environment variables are loaded
def test_env_vars_loaded():
    """Verify that environment variables from .django are loaded correctly (OCFL 1.1 structure)."""
    # Check specific environment variables for base patterns
    assert os.environ.get('COLLECTION_PATH_PATTERN') == '{collection_id}/{collection_id}'
    assert os.environ.get('BUNDLE_PATH_PATTERN') == '{collection_id}/{bundle_id}'

    # OCFL 1.1: resources in v1/content/ (no data subdirectory)
    if 'RESOURCE_PATH_PATTERN' in os.environ:
        resource_pattern = os.environ.get('RESOURCE_PATH_PATTERN')
        assert '/v1/content/' in resource_pattern

    # OCFL 1.1: metadata in v1/metadata/ (not v1/content/)
    if 'COLLECTION_XML_PATH' in os.environ:
        collection_xml = os.environ.get('COLLECTION_XML_PATH')
        assert collection_xml is None or collection_xml == '{collection_id}/{collection_id}/v1/metadata/{collection_id}.xml'

    if 'BUNDLE_XML_PATH' in os.environ:
        bundle_xml = os.environ.get('BUNDLE_XML_PATH')
        assert bundle_xml is None or bundle_xml == '{collection_id}/{bundle_id}/v1/metadata/{bundle_id}.xml'

    print(f"Environment variables loaded: {dict((k,v) for k,v in os.environ.items() if k.endswith('_PATH') or k.endswith('_PATTERN'))}")

# Use mock_s3 fixture from conftest.py

@pytest.fixture
def discovery_service(mock_s3):
    """Create a FileDiscoveryService with mock S3 client"""
    service = FileDiscoveryService()
    # Override the bucket names for testing
    service.production_bucket = TEST_BUCKET_NAME
    service.ingest_bucket = TEST_INGEST_BUCKET
    # Override the S3 client with our mock client
    service.s3_client = mock_s3
    
    # Debug print the path structure
    print(f"Service path structure: {service.path_structure}")
    
    return service

# Test path pattern formatting
def test_discovery_service_initialization(discovery_service):
    """Test that the FileDiscoveryService initializes correctly"""
    assert discovery_service is not None
    assert discovery_service.path_structure is not None
    assert discovery_service.s3_client is not None

def test_collection_path(discovery_service):
    path = discovery_service.form_collection_path("algerien")
    assert path == "algerien/algerien"

def test_bundle_path(discovery_service):
    path = discovery_service.form_bundle_path("algerien", "bundle123")
    assert path == "algerien/bundle123"

def test_resource_path(discovery_service):
    """OCFL 1.1: resources directly in v1/content/ (no data subdirectory)"""
    path = discovery_service.form_resource_path("algerien", "bundle123", "audio.mp3")
    assert path == "algerien/bundle123/v1/content/audio.mp3"

def test_collection_xml_path(discovery_service):
    """OCFL 1.1: metadata in v1/metadata/ (not v1/content/)"""
    path = discovery_service.form_collection_xml_path("algerien")
    assert path == "algerien/algerien/v1/metadata/algerien.xml"

def test_bundle_xml_path(discovery_service):
    """OCFL 1.1: metadata in v1/metadata/ (not v1/content/)"""
    path = discovery_service.form_bundle_xml_path("algerien", "bundle123")
    assert path == "algerien/bundle123/v1/metadata/bundle123.xml"


# Test S3 operations with real folder structure
def test_find_collections_s3(mock_s3, discovery_service):
    """Test finding collections using the S3 API with a real directory structure (OCFL 1.1)"""
    # Create test collection folders with proper structure
    for collection_id in ["algerien", "alwateti"]:
        # Create collection XML file (OCFL 1.1: metadata in v1/metadata/)
        xml_path = f"{collection_id}/{collection_id}/v1/metadata/{collection_id}.xml"
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
    collection_xml_path = discovery_service.form_collection_xml_path(collection_id)
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=collection_xml_path,
        Body=f"<xml>Collection {collection_id}</xml>"
    )
    
    # Create test bundle folders with proper structure
    test_bundle_ids = ["alg_bundle_1", "alg_bundle_2"]
    for bundle_id in test_bundle_ids:
        # Create bundle XML file
        xml_path = discovery_service.form_bundle_xml_path(collection_id, bundle_id)
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
    assert "alg_bundle_1" in bundles
    assert "alg_bundle_2" in bundles
    assert "not_bundle" not in bundles

def test_find_resources_in_bundle_s3(mock_s3, discovery_service):
    """Test finding resources in a bundle using the S3 API"""
    collection_id = "algerien"
    bundle_id = "alg_bundle_1"
    
    # Create bundle XML
    bundle_xml_path = discovery_service.form_bundle_xml_path(collection_id, bundle_id)
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=bundle_xml_path,
        Body=f"<xml>Bundle {bundle_id}</xml>"
    )
    
    # Create test resources
    # Use the service to format the base resource path (excluding filename)
    resource_pattern = discovery_service.get_resource_path_pattern()
    prefix_pattern = resource_pattern.rsplit('{resource_filename}', 1)[0]
    resources_prefix = prefix_pattern.format(collection_id=collection_id, bundle_id=bundle_id)
    
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
    """Test finding both collection and bundle XML files using the S3 API
       with a realistic sibling structure (like 'zaghawa')."""
    # Define the zaghawa structure IDs
    prefix = "zaghawa/"
    collection_id = "zaghawa"
    bundle_ids = [
        "zag_eoi_20141009_1",
        "zag_eoi_20141016_1",
        "zag_eoi_20141016_2"
    ]
    
    # Create the structure in S3
    # Collection
    collection_xml_path = discovery_service.form_collection_xml_path(collection_id)
    # Ensure the path starts with the prefix for this test structure
    assert collection_xml_path.startswith(f"{prefix}{collection_id}/") 
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=collection_xml_path,
        Body=f"<xml>Collection {collection_id}</xml>"
    )
    # Add a placeholder file to ensure the directory is listed
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=f"{prefix}{collection_id}/0=ocfl_object_1.0", 
        Body="placeholder"
    )
        
    # Create bundles
    expected_bundle_xml_paths = []
    for bundle_id in bundle_ids:
        # IMPORTANT: Use the identified collection_id when forming the bundle path
        bundle_xml_path = discovery_service.form_bundle_xml_path(collection_id, bundle_id)
        # Ensure the path starts with the correct sibling prefix for this test
        assert bundle_xml_path.startswith(f"{prefix}{bundle_id}/")
        expected_bundle_xml_paths.append(bundle_xml_path)
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=bundle_xml_path,
            Body=f"<xml>Bundle {bundle_id}</xml>"
        )
        # Add a placeholder file
        mock_s3.put_object(
            Bucket=TEST_BUCKET_NAME,
            Key=f"{prefix}{bundle_id}/0=ocfl_object_1.0", 
            Body="placeholder"
        )

    # Add another unrelated prefix to ensure filtering works
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key="other_prefix/some_file.txt",
        Body="ignore me"
    )

    # Call the method with the specific prefix
    result = discovery_service.find_collection_and_bundle_xmls_s3(TEST_BUCKET_NAME, prefix=prefix)
    
    # --- DEBUG: Print the result to see what's found ---
    print("\n--- Result from test_find_collection_and_bundle_xmls_s3 (zaghawa structure) ---")
    print(f"Potential Collections: {result.get('potential_collection_xmls')}")
    print(f"Potential Bundles: {result.get('potential_bundle_xmls')}")
    print("-----------------------------------------------------------------------------\n")
    # ---------------------------------------------------

    # Check results
    # Should find exactly one collection XML under the zaghawa prefix
    assert len(result['potential_collection_xmls']) == 1, f"Expected 1 collection, found {len(result['potential_collection_xmls'])}"
    assert collection_xml_path in result['potential_collection_xmls']
    
    # Should find exactly three bundle XMLs associated with the zaghawa collection
    assert len(result['potential_bundle_xmls']) == 3, f"Expected 3 bundles, found {len(result['potential_bundle_xmls'])}"
    for expected_path in expected_bundle_xml_paths:
        assert expected_path in result['potential_bundle_xmls'], f"Expected bundle path {expected_path} not found in results"

def test_get_collection_xml(mock_s3, discovery_service):
    """Test retrieving a collection XML file"""
    collection_id = "algerien"
    xml_content = b"<xml>Collection content</xml>"
    
    # Create the collection XML in S3
    collection_xml_path = discovery_service.form_collection_xml_path(collection_id)
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=collection_xml_path,
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
    bundle_id = "alg_bundle_1"
    xml_content = b"<xml>Bundle content</xml>"
    
    # Create the bundle XML in S3
    bundle_xml_path = discovery_service.form_bundle_xml_path(collection_id, bundle_id)
    mock_s3.put_object(
        Bucket=TEST_BUCKET_NAME,
        Key=bundle_xml_path,
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
    bundle_id = "alg_bundle_1"
    resource_filename = "audio.mp3"
    resource_content = b"Binary audio content"
    
    # Create the resource in S3
    resource_key = discovery_service.form_resource_path(collection_id, bundle_id, resource_filename)
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
    bundle_id = "alg_bundle_1"
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
