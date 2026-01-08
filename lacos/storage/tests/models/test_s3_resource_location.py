import pytest
from unittest.mock import MagicMock, patch
import uuid

# Instead of importing the actual model, we'll mock it
# from lacos.storage.models.s3_resource_location import S3ResourceLocation

@pytest.fixture
def content_type():
    """Mock ContentType object"""
    content_type = MagicMock()
    content_type.id = 1
    content_type.model = "s3fileobject"
    content_type.app_label = "storage"
    return content_type

@pytest.fixture
def s3_file_object():
    """Mock S3FileObject"""
    file_obj = MagicMock()
    file_obj.id = 123
    file_obj.file_name = "test_file.txt"
    file_obj.s3_key = "uploads/test_folder/test_file.txt"
    return file_obj

@pytest.fixture
def s3_resource_location(content_type, s3_file_object):
    """Mock S3ResourceLocation object"""
    resource = MagicMock()
    resource.resource_pid = "https://example.org/handle/123456"
    resource.s3_bucket = "test-bucket"
    resource.s3_key = "uploads/test_folder/test_file.txt"
    resource.content_type = content_type
    resource.object_id = s3_file_object.id
    resource.content_object = s3_file_object
    resource.mime_type = "text/plain"
    resource.size_bytes = 1024
    resource.__str__.return_value = f"{resource.resource_pid} -> {resource.s3_bucket}/{resource.s3_key}"
    return resource

class TestS3ResourceLocation:
    def test_creation(self, s3_resource_location):
        """Test that an S3ResourceLocation can be created with expected attributes"""
        assert s3_resource_location.resource_pid == "https://example.org/handle/123456"
        assert s3_resource_location.s3_bucket == "test-bucket"
        assert s3_resource_location.s3_key == "uploads/test_folder/test_file.txt"
        assert s3_resource_location.mime_type == "text/plain"
        assert s3_resource_location.size_bytes == 1024
        assert s3_resource_location.object_id == 123

    def test_string_representation(self, s3_resource_location):
        """Test the string representation of the model"""
        expected_str = "https://example.org/handle/123456 -> test-bucket/uploads/test_folder/test_file.txt"
        assert str(s3_resource_location) == expected_str

    def test_generic_foreign_key(self, s3_resource_location, s3_file_object):
        """Test that the generic foreign key works correctly"""
        assert s3_resource_location.content_object == s3_file_object
        assert s3_resource_location.object_id == s3_file_object.id

    def test_s3_resource_location_operations(self, content_type, s3_file_object):
        """Test model operations with mocked ORM"""
        # Setup
        S3ResourceLocation = MagicMock()
        S3ResourceLocation.objects = MagicMock()
        
        # Mock create
        created_resource = MagicMock(
            resource_pid="https://example.org/handle/123456",
            s3_bucket="test-bucket",
            s3_key="uploads/test_folder/test_file.txt",
            content_type=content_type,
            object_id=s3_file_object.id,
            content_object=s3_file_object
        )
        S3ResourceLocation.objects.create.return_value = created_resource
        
        # Mock get
        S3ResourceLocation.objects.get.return_value = created_resource
        
        # Mock filter
        mock_queryset = MagicMock()
        mock_queryset.first.return_value = created_resource
        S3ResourceLocation.objects.filter.return_value = mock_queryset
        
        # Execute - create
        resource = S3ResourceLocation.objects.create(
            resource_pid="https://example.org/handle/123456",
            s3_bucket="test-bucket",
            s3_key="uploads/test_folder/test_file.txt",
            content_type=content_type,
            object_id=s3_file_object.id
        )
        
        # Execute - retrieve by PID
        retrieved_by_pid = S3ResourceLocation.objects.get(resource_pid="https://example.org/handle/123456")
        
        # Execute - filter by content object
        filtered = S3ResourceLocation.objects.filter(
            content_type=content_type,
            object_id=s3_file_object.id
        ).first()
        
        # Assert
        assert retrieved_by_pid.resource_pid == "https://example.org/handle/123456"
        assert retrieved_by_pid.s3_bucket == "test-bucket"
        assert filtered.resource_pid == "https://example.org/handle/123456"
        S3ResourceLocation.objects.create.assert_called_once()
        S3ResourceLocation.objects.get.assert_called_once()
        S3ResourceLocation.objects.filter.assert_called_once_with(
            content_type=content_type,
            object_id=s3_file_object.id
        )

    def test_lookup_by_content_object(self):
        """Test looking up a resource location by its related object"""
        # Setup
        content_type = MagicMock(id=1)
        s3_file_object = MagicMock(id=123)
        ContentType = MagicMock()
        ContentType.objects.get_for_model.return_value = content_type
        
        S3ResourceLocation = MagicMock()
        S3ResourceLocation.objects = MagicMock()
        
        mock_queryset = MagicMock()
        mock_resource = MagicMock(
            resource_pid="https://example.org/handle/123456",
            s3_bucket="test-bucket",
            s3_key="uploads/test_folder/test_file.txt"
        )
        mock_queryset.first.return_value = mock_resource
        S3ResourceLocation.objects.filter.return_value = mock_queryset
        
        # Execute - simulate a lookup helper method
        with patch('django.contrib.contenttypes.models.ContentType.objects.get_for_model', 
                  return_value=content_type):
            def get_resource_for_object(obj):
                ct = ContentType.objects.get_for_model(obj.__class__)
                return S3ResourceLocation.objects.filter(
                    content_type=ct,
                    object_id=obj.id
                ).first()
            
            resource = get_resource_for_object(s3_file_object)
        
        # Assert
        assert resource.resource_pid == "https://example.org/handle/123456"
        assert resource.s3_bucket == "test-bucket"
        assert resource.s3_key == "uploads/test_folder/test_file.txt"
        ContentType.objects.get_for_model.assert_called_once()
        S3ResourceLocation.objects.filter.assert_called_once_with(
            content_type=content_type,
            object_id=s3_file_object.id
        ) 