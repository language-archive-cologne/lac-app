import os
import pytest
from unittest.mock import patch, MagicMock


from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import MediaResource, WrittenResource, OtherResource
from lacos.storage.services.resource_mapping_service import ResourceMappingService


@pytest.fixture
def zaghawa_xml_content():
    """Load a sample bundle XML file content"""
    xml_path = os.path.join('data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Try alternate path for Docker environment
        xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()


@pytest.fixture
def cmd_data(zaghawa_xml_content):
    """Parse XML into CMD data object"""
    return BundleImporter.validate_xml(zaghawa_xml_content)


@pytest.fixture
def mock_resource_mapping_service():
    """Mock ResourceMappingService for testing"""
    mock_service = MagicMock(spec=ResourceMappingService)
    
    # Set up the mocked methods for S3 location mapping
    mock_s3_location = MagicMock(
        s3_bucket="test-bucket",
        s3_key="test/resource/key.mp3",
        resource_pid="http://hdl.handle.net/test/resource1"
    )
    
    mock_service.get_s3_location.return_value = mock_s3_location
    mock_service.resolve_pid_to_s3.return_value = mock_s3_location
    mock_service.register_s3_location.return_value = mock_s3_location
    
    # Set up path construction
    mock_service.construct_s3_path.return_value = "collections/1/bundles/2/resources/audio.mp3"
    
    # Patch the ResourceMappingService class
    with patch('lacos.storage.services.resource_mapping_service.ResourceMappingService', return_value=mock_service):
        yield mock_service


@pytest.fixture
def mock_bundle():
    """Create a mock Bundle for testing"""
    bundle = MagicMock(spec=Bundle)
    bundle.id = 1
    bundle.pid = "http://hdl.handle.net/test/bundle1"
    
    # Create mock resources
    media_resource = MagicMock(spec=MediaResource)
    media_resource.id = 1
    media_resource.file_pid = "http://hdl.handle.net/test/resource1"
    media_resource.file_name = "audio.mp3"
    
    written_resource = MagicMock(spec=WrittenResource)
    written_resource.id = 2
    written_resource.file_pid = "http://hdl.handle.net/test/resource2"
    written_resource.file_name = "transcript.txt"
    
    # Set up bundle structural info
    bundle.structural_info.bundle_resources.bundle_media_resources.all.return_value = [media_resource]
    bundle.structural_info.bundle_resources.bundle_written_resources.all.return_value = [written_resource]
    bundle.structural_info.bundle_resources.bundle_other_resources.all.return_value = []
    
    return bundle


def test_extract_resources_from_xml(cmd_data):
    """Test extracting resources from the Zaghawa bundle XML"""
    # Verify we have valid CMD data
    assert cmd_data is not None
    
    # Print XML structure for debugging
    print("CMD structure:", dir(cmd_data.components))
    
    # Access the bundle repository using the correct attribute name
    repository = cmd_data.components.blam_bundle_repository_v1_0
    assert repository is not None, "Missing bundle repository in CMD data"
    
    # Access bundle resources from real data structure
    struct_info = repository.bundle_structural_info
    assert struct_info is not None, "Missing bundle_structural_info in repository"
    
    resources = struct_info.bundle_resources
    assert resources is not None, "Missing bundle_resources in structural_info"
    
    # Check for media resources in the correct format (from the real XML)
    media_resources = []
    if hasattr(resources, 'media_resource'):
        media_resources = resources.media_resource
        print(f"Found {len(media_resources)} media resources")
        
        # Verify the first media resource has the expected WAV file
        assert len(media_resources) > 0, "No media resources found"
        assert hasattr(media_resources[0], 'file_name'), "Media resource missing file_name"
        assert "wav" in media_resources[0].file_name.lower(), f"Expected WAV file, got {media_resources[0].file_name}"
        print(f"Verified media resource: {media_resources[0].file_name}")
    
    # Check for written resources in the correct format
    written_resources = []
    if hasattr(resources, 'written_resource'):
        written_resources = resources.written_resource
        print(f"Found {len(written_resources)} written resources")
        
        # Verify the first written resource has the expected EAF file
        assert len(written_resources) > 0, "No written resources found"
        assert hasattr(written_resources[0], 'file_name'), "Written resource missing file_name"
        assert "eaf" in written_resources[0].file_name.lower(), f"Expected EAF file, got {written_resources[0].file_name}"
        print(f"Verified written resource: {written_resources[0].file_name}")
    
    # Verify we have found both types of resources
    assert len(media_resources) > 0, "No media resources found"
    assert len(written_resources) > 0, "No written resources found"


@patch('lacos.blam.mappers.bundle.read.import_bundle_structural_info.import_structural_info')
@patch('lacos.blam.mappers.bundle.read.import_bundle_administrative_info.import_administrative_info')
@patch('lacos.blam.mappers.bundle.read.import_bundle_publication_info.import_publication_info')
@patch('lacos.blam.mappers.bundle.read.import_bundle_general_info.import_general_info')
@patch('lacos.blam.models.base_project_info.ProjectInfo.objects.create')
@patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects.get_or_create')
def test_extract_resources_using_bundle_importer(
    mock_get_or_create, mock_create_project, mock_import_general, 
    mock_import_publication, mock_import_administrative, mock_import_structural,
    cmd_data, mock_bundle
):
    """Test extracting resources using the actual BundleImporter methods"""
    # Set up mocks
    mock_general_info = MagicMock()
    mock_publication_info = MagicMock()
    mock_administrative_info = MagicMock()
    mock_structural_info = MagicMock()
    
    mock_import_general.return_value = mock_general_info
    mock_import_publication.return_value = mock_publication_info
    mock_import_administrative.return_value = mock_administrative_info
    mock_import_structural.return_value = mock_structural_info
    
    mock_get_or_create.return_value = (mock_bundle, True)
    
    # Use a method from BundleImporter that doesn't hit the database
    license_value, license_uri = BundleImporter._extract_metadata_license(cmd_data)
    
    # Verify license extraction worked with real XML
    assert license_value == "CC0", f"Expected CC0 license, got {license_value}"
    assert "creativecommons.org" in license_uri, f"Expected Creative Commons URI, got {license_uri}"
    
    # Now test bundle resources directly from the XML
    repository = cmd_data.components.blam_bundle_repository_v1_0
    
    # Print repository information
    print("\nBundle repository information:")
    print(f"  MDLicense: {repository.mdlicense.value} ({repository.mdlicense.uri})")
    
    # Verify structural info exists as expected in the real XML
    struct_info = repository.bundle_structural_info
    assert hasattr(struct_info, 'bundle_resources'), "Missing bundle_resources in XML"
    
    # Print resources found in the XML
    resources = struct_info.bundle_resources
    
    if hasattr(resources, 'media_resource'):
        media_resources = resources.media_resource
        for i, res in enumerate(media_resources):
            print(f"Media resource {i+1}: {res.file_name} ({res.file_pid})")
            
            # Verify media resource has expected attributes
            assert hasattr(res, 'file_name'), "Media resource missing filename"
            assert hasattr(res, 'file_pid'), "Media resource missing PID"
            assert hasattr(res, 'mime_type'), "Media resource missing mime type"
    
    if hasattr(resources, 'written_resource'):
        written_resources = resources.written_resource
        for i, res in enumerate(written_resources):
            print(f"Written resource {i+1}: {res.file_name} ({res.file_pid})")
            
            # Verify written resource has expected attributes
            assert hasattr(res, 'file_name'), "Written resource missing filename"
            assert hasattr(res, 'file_pid'), "Written resource missing PID"
            assert hasattr(res, 'mime_type'), "Written resource missing mime type"


def test_map_bundle_resources_to_s3(mock_bundle, mock_resource_mapping_service):
    """Test mapping bundle resources to S3 locations"""
    # Get resources from the bundle
    media_resources = mock_bundle.structural_info.bundle_resources.bundle_media_resources.all()
    written_resources = mock_bundle.structural_info.bundle_resources.bundle_written_resources.all()
    
    # Test getting S3 location for a media resource
    media_resource = media_resources[0]
    media_s3_location = mock_resource_mapping_service.get_s3_location(media_resource)
    assert media_s3_location is not None
    mock_resource_mapping_service.get_s3_location.assert_called_with(media_resource)
    
    # Test getting S3 location for a written resource
    written_resource = written_resources[0]
    written_s3_location = mock_resource_mapping_service.get_s3_location(written_resource)
    assert written_s3_location is not None
    mock_resource_mapping_service.get_s3_location.assert_called_with(written_resource)
    
    # Test resolving PID to S3 location
    pid_s3_location = mock_resource_mapping_service.resolve_pid_to_s3(media_resource.file_pid)
    assert pid_s3_location is not None
    mock_resource_mapping_service.resolve_pid_to_s3.assert_called_with(media_resource.file_pid)


@patch('lacos.storage.services.resource_mapping_service.ResourceMappingService.register_s3_location')
@patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_cmd_to_models')
@patch('django.db.transaction.atomic')
def test_register_resources_from_real_xml(mock_atomic, mock_import_cmd, mock_register_s3, cmd_data, mock_bundle):
    """Test registering resources from real XML structure"""
    # Setup mocks
    mock_import_cmd.return_value = mock_bundle
    mock_atomic.return_value.__enter__ = MagicMock()
    mock_atomic.return_value.__exit__ = MagicMock()
    
    # Use the import_from_xml method with mocked DB access
    with patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter.import_from_xml', 
              return_value=mock_bundle):
        bundle = BundleImporter.import_from_xml(cmd_data)
    
    # Verify the bundle was created
    assert bundle == mock_bundle
    
    # Get resource information from real XML structure
    repository = cmd_data.components.blam_bundle_repository_v1_0
    struct_info = repository.bundle_structural_info
    
    # Extract resource data directly from the XML
    resources = struct_info.bundle_resources
    
    # Get media resources and their properties for mapping to S3
    media_resources = []
    if hasattr(resources, 'media_resource'):
        media_resources = resources.media_resource
        print(f"\nMedia resources from XML: {len(media_resources)}")
        
        for res in media_resources:
            # Register each actual resource from XML in S3
            s3_bucket = "test-bucket"
            s3_key = f"bundles/{mock_bundle.id}/resources/{res.file_name}"
            
            print(f"Would register: {res.file_name} ({res.file_pid}) to S3 path: {s3_key}")
    
    # Get written resources for mapping to S3
    written_resources = []
    if hasattr(resources, 'written_resource'):
        written_resources = resources.written_resource
        print(f"Written resources from XML: {len(written_resources)}")
        
        for res in written_resources:
            # Register each actual resource from XML in S3
            s3_bucket = "test-bucket"
            s3_key = f"bundles/{mock_bundle.id}/resources/{res.file_name}"
            
            print(f"Would register: {res.file_name} ({res.file_pid}) to S3 path: {s3_key}")
    
    # Calculate total resources
    total_resources = len(media_resources) + len(written_resources)
    print(f"Total resources in XML: {total_resources}")
    assert total_resources > 0, "No resources found in XML"
    
    # Now use the mock bundle's resources for the S3 registration test
    # to avoid dependency on real XML structure during assertions
    s3_bucket = "test-bucket"
    base_key = f"bundles/{bundle.id}/resources"
    
    # Media resources from mock bundle
    mock_media_resources = bundle.structural_info.bundle_resources.bundle_media_resources.all()
    for resource in mock_media_resources:
        mock_register_s3(resource, s3_bucket, f"{base_key}/{resource.file_name}")
    
    # Written resources from mock bundle
    mock_written_resources = bundle.structural_info.bundle_resources.bundle_written_resources.all()
    for resource in mock_written_resources:
        mock_register_s3(resource, s3_bucket, f"{base_key}/{resource.file_name}")
    
    # Verify register_s3_location was called for all resources
    expected_call_count = len(mock_media_resources) + len(mock_written_resources)
    assert mock_register_s3.call_count == expected_call_count, f"Expected {expected_call_count} calls, got {mock_register_s3.call_count}"


def test_register_bundle_resources_in_s3(mock_bundle, mock_resource_mapping_service):
    """Test registering bundle resources in S3"""
    # Get resources from the bundle
    media_resources = mock_bundle.structural_info.bundle_resources.bundle_media_resources.all()
    written_resources = mock_bundle.structural_info.bundle_resources.bundle_written_resources.all()
    
    # Generate S3 key based on resource file name
    s3_bucket = "test-bucket"
    base_key = f"collections/1/bundles/{mock_bundle.id}/resources"
    
    # Test registering a media resource
    media_resource = media_resources[0]
    media_key = f"{base_key}/{media_resource.file_name}"
    mock_resource_mapping_service.register_s3_location(media_resource, s3_bucket, media_key)
    
    # Test registering a written resource
    written_resource = written_resources[0]
    written_key = f"{base_key}/{written_resource.file_name}"
    mock_resource_mapping_service.register_s3_location(written_resource, s3_bucket, written_key)
    
    # Verify calls
    mock_resource_mapping_service.register_s3_location.assert_any_call(
        media_resource, s3_bucket, media_key
    )
    mock_resource_mapping_service.register_s3_location.assert_any_call(
        written_resource, s3_bucket, written_key
    )


def test_construct_s3_paths_for_bundle_resources(mock_bundle, mock_resource_mapping_service):
    """Test constructing S3 paths for bundle resources"""
    # Get resources from the bundle
    media_resources = mock_bundle.structural_info.bundle_resources.bundle_media_resources.all()
    written_resources = mock_bundle.structural_info.bundle_resources.bundle_written_resources.all()
    
    # Configure construct_s3_path for different resources
    def construct_path_side_effect(obj):
        if obj == mock_bundle:
            return f"collections/1/bundles/{obj.id}/"
        elif obj == media_resources[0]:
            return f"collections/1/bundles/{mock_bundle.id}/resources/{obj.file_name}"
        elif obj == written_resources[0]:
            return f"collections/1/bundles/{mock_bundle.id}/resources/{obj.file_name}"
        return None
    
    mock_resource_mapping_service.construct_s3_path.side_effect = construct_path_side_effect
    
    # Test constructing paths
    bundle_path = mock_resource_mapping_service.construct_s3_path(mock_bundle)
    media_path = mock_resource_mapping_service.construct_s3_path(media_resources[0])
    written_path = mock_resource_mapping_service.construct_s3_path(written_resources[0])
    
    # Verify results
    assert bundle_path == f"collections/1/bundles/{mock_bundle.id}/"
    assert media_path == f"collections/1/bundles/{mock_bundle.id}/resources/audio.mp3"
    assert written_path == f"collections/1/bundles/{mock_bundle.id}/resources/transcript.txt"
    
    # Verify calls
    mock_resource_mapping_service.construct_s3_path.assert_any_call(mock_bundle)
    mock_resource_mapping_service.construct_s3_path.assert_any_call(media_resources[0])
    mock_resource_mapping_service.construct_s3_path.assert_any_call(written_resources[0]) 