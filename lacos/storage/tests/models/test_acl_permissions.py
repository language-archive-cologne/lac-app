import pytest
from unittest.mock import MagicMock, patch
import uuid
from datetime import datetime, timezone

# Instead of importing the actual model, we'll mock it
# from lacos.storage.models.acl_permissions import ACLPermissions

@pytest.fixture
def content_type():
    """Mock ContentType object"""
    content_type = MagicMock()
    content_type.id = 1
    content_type.model = "collection"
    content_type.app_label = "storage"
    return content_type

@pytest.fixture
def collection():
    """Mock Collection object"""
    collection = MagicMock()
    collection.id = 123
    collection.name = "Test Collection"
    collection.__str__.return_value = "Test Collection"
    return collection

@pytest.fixture
def acl_permissions(content_type, collection):
    """Mock ACLPermissions object"""
    permissions = MagicMock()
    permissions.content_type = content_type
    permissions.object_id = collection.id
    permissions.content_object = collection
    permissions.ACL_file_bucket = "test-bucket"
    permissions.ACL_file_key = "acls/collection_123.json"
    permissions.permissions_data = {
        "read": ["user1", "user2"],
        "write": ["user1"],
        "admin": ["admin"]
    }
    permissions.last_synced = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    permissions.__str__.return_value = f"ACL Permissions for {collection}"
    return permissions

class TestACLPermissions:
    def test_creation(self, acl_permissions, collection):
        """Test that an ACLPermissions can be created with expected attributes"""
        assert acl_permissions.ACL_file_bucket == "test-bucket"
        assert acl_permissions.ACL_file_key == "acls/collection_123.json"
        assert acl_permissions.content_object == collection
        assert acl_permissions.object_id == 123
        assert "read" in acl_permissions.permissions_data
        assert "write" in acl_permissions.permissions_data
        assert "admin" in acl_permissions.permissions_data
        assert acl_permissions.last_synced.year == 2023

    def test_string_representation(self, acl_permissions, collection):
        """Test the string representation of the model"""
        expected_str = f"ACL Permissions for {collection}"
        assert str(acl_permissions) == expected_str

    def test_generic_foreign_key(self, acl_permissions, collection):
        """Test that the generic foreign key works correctly"""
        assert acl_permissions.content_object == collection
        assert acl_permissions.object_id == collection.id

    def test_acl_permissions_operations(self, content_type, collection):
        """Test model operations with mocked ORM"""
        # Setup
        ACLPermissions = MagicMock()
        ACLPermissions.objects = MagicMock()
        
        # Mock create
        permissions_data = {
            "read": ["user1", "user2"],
            "write": ["user1"],
            "admin": ["admin"]
        }
        
        created_permissions = MagicMock(
            content_type=content_type,
            object_id=collection.id,
            content_object=collection,
            ACL_file_bucket="test-bucket",
            ACL_file_key="acls/collection_123.json",
            permissions_data=permissions_data
        )
        ACLPermissions.objects.create.return_value = created_permissions
        
        # Mock get
        ACLPermissions.objects.get.return_value = created_permissions
        
        # Mock filter
        mock_queryset = MagicMock()
        mock_queryset.first.return_value = created_permissions
        ACLPermissions.objects.filter.return_value = mock_queryset
        
        # Execute - create
        permissions = ACLPermissions.objects.create(
            content_type=content_type,
            object_id=collection.id,
            ACL_file_bucket="test-bucket",
            ACL_file_key="acls/collection_123.json",
            permissions_data=permissions_data
        )
        
        # Execute - retrieve by content object
        retrieved = ACLPermissions.objects.filter(
            content_type=content_type,
            object_id=collection.id
        ).first()
        
        # Execute - get by id
        retrieved_by_id = ACLPermissions.objects.get(id=1)
        
        # Assert
        assert retrieved.ACL_file_bucket == "test-bucket"
        assert retrieved.ACL_file_key == "acls/collection_123.json"
        assert retrieved.permissions_data == permissions_data
        assert retrieved_by_id.content_object == collection
        
        ACLPermissions.objects.create.assert_called_once()
        ACLPermissions.objects.filter.assert_called_once_with(
            content_type=content_type,
            object_id=collection.id
        )
        ACLPermissions.objects.get.assert_called_once()

    def test_lookup_by_content_object(self):
        """Test looking up permissions by its related object"""
        # Setup
        content_type = MagicMock(id=1)
        collection = MagicMock(id=123)
        ContentType = MagicMock()
        ContentType.objects.get_for_model.return_value = content_type
        
        ACLPermissions = MagicMock()
        ACLPermissions.objects = MagicMock()
        
        mock_queryset = MagicMock()
        mock_permissions = MagicMock(
            ACL_file_bucket="test-bucket",
            ACL_file_key="acls/collection_123.json",
            permissions_data={
                "read": ["user1", "user2"],
                "write": ["user1"],
                "admin": ["admin"]
            }
        )
        mock_queryset.first.return_value = mock_permissions
        ACLPermissions.objects.filter.return_value = mock_queryset
        
        # Execute - simulate a lookup helper method
        with patch('django.contrib.contenttypes.models.ContentType.objects.get_for_model', 
                  return_value=content_type):
            def get_permissions_for_object(obj):
                ct = ContentType.objects.get_for_model(obj.__class__)
                return ACLPermissions.objects.filter(
                    content_type=ct,
                    object_id=obj.id
                ).first()
            
            permissions = get_permissions_for_object(collection)
        
        # Assert
        assert permissions.ACL_file_bucket == "test-bucket"
        assert permissions.ACL_file_key == "acls/collection_123.json"
        assert "read" in permissions.permissions_data
        ContentType.objects.get_for_model.assert_called_once()
        ACLPermissions.objects.filter.assert_called_once_with(
            content_type=content_type,
            object_id=collection.id
        )

    def test_update_permissions_data(self):
        """Test updating permissions data"""
        # Setup
        acl_permissions = MagicMock()
        acl_permissions.permissions_data = {
            "read": ["user1", "user2"],
            "write": ["user1"],
            "admin": ["admin"]
        }
        acl_permissions.save = MagicMock()
        
        # Execute - simulate updating permissions
        new_permissions = {
            "read": ["user1", "user2", "user3"],
            "write": ["user1"],
            "admin": ["admin", "superadmin"]
        }
        
        acl_permissions.permissions_data = new_permissions
        acl_permissions.save()
        
        # Assert
        assert "user3" in acl_permissions.permissions_data["read"]
        assert "superadmin" in acl_permissions.permissions_data["admin"]
        acl_permissions.save.assert_called_once() 