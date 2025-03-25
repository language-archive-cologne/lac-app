import pytest
from unittest.mock import patch, MagicMock, call

from django.contrib.contenttypes.models import ContentType

from lacos.blam.models.bundle.bundle_structural_info import MediaResource, WrittenResource, OtherResource
from lacos.storage.services.resource_mapping_service import ResourceMappingService
from lacos.storage.models.s3_resource_location import S3ResourceLocation


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
def mock_content_type():
    """Mock ContentType for testing"""
    mock_ct = MagicMock()
    mock_ct.objects.get_for_model.return_value = MagicMock(id=1)
    return mock_ct


@pytest.fixture
def mock_s3_resource_location():
    """Mock S3ResourceLocation for testing"""
    mock_location = MagicMock(spec=S3ResourceLocation)
    mock_location.s3_bucket = "test-bucket"
    mock_location.s3_key = "test/resource/key.mp3"
    mock_location.resource_pid = "http://hdl.handle.net/test/resource1"
    
    # Mock the model manager
    mock_manager = MagicMock()
    mock_manager.get.return_value = mock_location
    mock_manager.filter.return_value.first.return_value = mock_location
    mock_manager.create.return_value = mock_location
    mock_manager.update_or_create.return_value = (mock_location, True)
    
    # Patch the model's objects attribute
    with patch('lacos.storage.models.s3_resource_location.S3ResourceLocation.objects', mock_manager):
        yield mock_location


def test_get_s3_location_by_resource(mock_content_type, mock_s3_resource_location, mock_resource_mapping_service):
    """Test getting S3 location by a resource object"""
    # Create mock resource
    resource = MagicMock(spec=MediaResource)
    resource.id = 1
    resource.file_pid = "http://hdl.handle.net/test/resource1"
    
    # Test getting S3 location
    location = mock_resource_mapping_service.get_s3_location(resource)
    
    # Verify correct calls were made
    assert location is not None
    assert location.s3_bucket == "test-bucket"
    assert location.s3_key == "test/resource/key.mp3"
    assert location.resource_pid == "http://hdl.handle.net/test/resource1"
    mock_resource_mapping_service.get_s3_location.assert_called_once_with(resource)


def test_resolve_pid_to_s3(mock_s3_resource_location, mock_resource_mapping_service):
    """Test resolving a PID to an S3 location"""
    # Test PID
    pid = "http://hdl.handle.net/test/resource1"
    
    # Test resolving PID to S3 location
    location = mock_resource_mapping_service.resolve_pid_to_s3(pid)
    
    # Verify correct calls were made
    assert location is not None
    assert location.s3_bucket == "test-bucket"
    assert location.s3_key == "test/resource/key.mp3"
    assert location.resource_pid == "http://hdl.handle.net/test/resource1"
    mock_resource_mapping_service.resolve_pid_to_s3.assert_called_once_with(pid)


def test_register_s3_location(mock_content_type, mock_s3_resource_location, mock_resource_mapping_service):
    """Test registering an S3 location for a resource"""
    # Create mock resource
    resource = MagicMock(spec=MediaResource)
    resource.id = 1
    resource.file_pid = "http://hdl.handle.net/test/resource1"
    
    # Test bucket and key
    s3_bucket = "test-bucket"
    s3_key = "test/resources/audio.mp3"
    
    # Set up register_s3_location to return mock_s3_resource_location
    mock_resource_mapping_service.register_s3_location.return_value = mock_s3_resource_location
    
    # Call the method being tested
    location = mock_resource_mapping_service.register_s3_location(resource, s3_bucket, s3_key)
    
    # Verify correct calls were made
    assert location is not None
    assert location is mock_s3_resource_location
    mock_resource_mapping_service.register_s3_location.assert_called_once_with(resource, s3_bucket, s3_key)


def test_construct_s3_path(mock_resource_mapping_service):
    """Test constructing S3 paths based on object type"""
    # Create mock bundle
    bundle = MagicMock()
    bundle.id = 2
    
    # Create mock collection
    collection = MagicMock()
    collection.id = 1
    
    # Set up bundle's parent collection
    bundle.structural_info.is_member_of_collection = collection
    
    # Create mock resource
    resource = MagicMock(spec=MediaResource)
    resource.id = 3
    resource.file_name = "audio.mp3"
    resource.file_pid = "http://hdl.handle.net/test/resource1"
    
    # Configure construct_s3_path to return different paths based on input
    def construct_path_side_effect(obj):
        if obj == collection:
            return f"collections/{obj.id}/"
        elif obj == bundle:
            return f"collections/{obj.structural_info.is_member_of_collection.id}/bundles/{obj.id}/"
        elif obj == resource:
            return f"collections/1/bundles/2/resources/{obj.file_name}"
        return None
    
    mock_resource_mapping_service.construct_s3_path.side_effect = construct_path_side_effect
    
    # Test for different object types
    collection_path = mock_resource_mapping_service.construct_s3_path(collection)
    bundle_path = mock_resource_mapping_service.construct_s3_path(bundle)
    resource_path = mock_resource_mapping_service.construct_s3_path(resource)
    
    # Verify correct paths were constructed
    assert collection_path == "collections/1/"
    assert bundle_path == "collections/1/bundles/2/"
    assert resource_path == "collections/1/bundles/2/resources/audio.mp3"


def test_batch_register_resources(mock_resource_mapping_service):
    """Test registering multiple resources in a batch"""
    # Create mock resources
    resources = [
        MagicMock(spec=MediaResource, file_pid="http://hdl.handle.net/test/res1", id=1),
        MagicMock(spec=WrittenResource, file_pid="http://hdl.handle.net/test/res2", id=2),
        MagicMock(spec=OtherResource, file_pid="http://hdl.handle.net/test/res3", id=3)
    ]
    
    # Test bucket and base key
    s3_bucket = "test-bucket"
    s3_base_key = "test/resources"
    
    # Configure mock to call the register_s3_location method for each resource
    def batch_register_side_effect(res_list, bucket, base_key):
        for i, res in enumerate(res_list):
            mock_resource_mapping_service.register_s3_location(res, bucket, f"{base_key}/res{i+1}")
    
    mock_resource_mapping_service.batch_register_resources.side_effect = batch_register_side_effect
    
    # Test batch registration
    mock_resource_mapping_service.batch_register_resources(resources, s3_bucket, s3_base_key)
    
    # Verify the method was called
    mock_resource_mapping_service.batch_register_resources.assert_called_once_with(resources, s3_bucket, s3_base_key)
    
    # Verify register_s3_location was called for each resource
    assert mock_resource_mapping_service.register_s3_location.call_count == 3
    
    expected_calls = [
        call(resources[0], s3_bucket, f"{s3_base_key}/res1"),
        call(resources[1], s3_bucket, f"{s3_base_key}/res2"),
        call(resources[2], s3_bucket, f"{s3_base_key}/res3")
    ]
    mock_resource_mapping_service.register_s3_location.assert_has_calls(expected_calls, any_order=True) 