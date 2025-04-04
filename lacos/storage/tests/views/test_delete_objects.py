import uuid
import pytest
from unittest.mock import patch, MagicMock

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.views.crud import delete_blam_model
from lacos.storage.views.file_operations_views import delete_object

User = get_user_model()


@pytest.fixture
def admin_user():
    """Create a test admin user."""
    return User.objects.create_superuser(
        username='testadmin',
        email='testadmin@example.com',
        password='testpassword'
    )


@pytest.fixture
def authenticated_client(admin_user):
    """Create an authenticated client."""
    client = Client()
    client.login(username='testadmin', password='testpassword')
    return client


@pytest.fixture
def test_collection():
    """Create a test collection."""
    return Collection.objects.create(title="Test Collection")


@pytest.fixture
def test_bundle(test_collection):
    """Create a test bundle in the test collection."""
    return Bundle.objects.create(
        title="Test Bundle",
        collection=test_collection
    )


# BLAM Model Delete Tests
def test_delete_collection_success(authenticated_client, test_collection):
    """Test successful deletion of a Collection."""
    # Get the initial count
    initial_count = Collection.objects.count()
    
    # Make the delete request
    url = reverse('blam:delete_model', kwargs={
        'model_type': 'collection',
        'object_id': str(test_collection.id)
    })
    response = authenticated_client.post(url)
    
    # Check the response
    assert response.status_code == 200
    assert response.content.decode() == ""
    
    # Verify the collection was deleted
    assert Collection.objects.count() == initial_count - 1


def test_delete_bundle_success(authenticated_client, test_bundle):
    """Test successful deletion of a Bundle."""
    # Get the initial count
    initial_count = Bundle.objects.count()
    
    # Make the delete request
    url = reverse('blam:delete_model', kwargs={
        'model_type': 'bundle',
        'object_id': str(test_bundle.id)
    })
    response = authenticated_client.post(url)
    
    # Check the response
    assert response.status_code == 200
    assert response.content.decode() == ""
    
    # Verify the bundle was deleted
    assert Bundle.objects.count() == initial_count - 1


def test_delete_invalid_model_type(authenticated_client):
    """Test deletion with an invalid model type."""
    url = reverse('blam:delete_model', kwargs={
        'model_type': 'invalid_type',
        'object_id': str(uuid.uuid4())
    })
    response = authenticated_client.post(url)
    
    # Should return a bad request response
    assert response.status_code == 400


def test_delete_nonexistent_object(authenticated_client):
    """Test deletion of a non-existent object."""
    url = reverse('blam:delete_model', kwargs={
        'model_type': 'collection',
        'object_id': str(uuid.uuid4())  # Random UUID that doesn't exist
    })
    response = authenticated_client.post(url)
    
    # Should return a 404 not found
    assert response.status_code == 404


def test_htmx_blam_response(admin_user, test_bundle):
    """Test the response when requested via HTMX."""
    # Use RequestFactory to add HX-Request header
    factory = RequestFactory()
    url = reverse('blam:delete_model', kwargs={
        'model_type': 'bundle',
        'object_id': str(test_bundle.id)
    })
    request = factory.post(url, HTTP_HX_REQUEST='true')
    request.user = admin_user
    
    response = delete_blam_model(request, 'bundle', test_bundle.id)
    
    # Check the response
    assert response.status_code == 200
    assert response.content.decode() == ""


# Storage Object Delete Tests
@pytest.fixture
def s3_test_paths():
    """Define test paths for S3 objects."""
    return {
        'file_path': 'test/path/to/file.txt',
        'folder_path': 'test/path/to/folder',
        'bucket_type': 'ingest'
    }


@pytest.mark.parametrize("object_type,is_directory", [
    ('file', False),
    ('folder', True)
])
def test_delete_object_success(authenticated_client, s3_test_paths, object_type, is_directory):
    """Test successful deletion of a file or folder."""
    with patch('lacos.storage.views.file_operations_views.get_storage_service') as mock_get_service:
        # Mock the storage service
        mock_service = MagicMock()
        mock_service.delete_object.return_value = {'success': True}
        mock_get_service.return_value = mock_service
        
        # Get the path based on object type
        object_path = s3_test_paths['folder_path'] if object_type == 'folder' else s3_test_paths['file_path']
        
        # Make the delete request
        url = reverse('storage:delete_object', kwargs={
            'bucket_type': s3_test_paths['bucket_type'],
            'object_type': object_type,
            'object_path': object_path
        })
        response = authenticated_client.post(url)
        
        # Check the response
        assert response.status_code == 200
        
        # Verify the service was called correctly
        mock_service.delete_object.assert_called_once_with(
            bucket_name=f'lacos-{s3_test_paths["bucket_type"]}',
            object_path=object_path,
            is_directory=is_directory
        )


def test_delete_object_error(authenticated_client, s3_test_paths):
    """Test error handling when deleting an object."""
    with patch('lacos.storage.views.file_operations_views.get_storage_service') as mock_get_service:
        # Mock the storage service to return an error
        mock_service = MagicMock()
        mock_service.delete_object.return_value = {
            'success': False,
            'error': 'Object not found'
        }
        mock_get_service.return_value = mock_service
        
        # Make the delete request
        url = reverse('storage:delete_object', kwargs={
            'bucket_type': s3_test_paths['bucket_type'],
            'object_type': 'file',
            'object_path': s3_test_paths['file_path']
        })
        response = authenticated_client.post(url)
        
        # Check the response (should still be 200 for HTMX to handle)
        assert response.status_code == 200
        
        # The response should include the error message
        assert 'error' in response.content.decode()
        assert 'Object not found' in response.content.decode()


def test_delete_invalid_object_type(authenticated_client, s3_test_paths):
    """Test deletion with an invalid object type."""
    with patch('lacos.storage.views.file_operations_views.get_storage_service') as mock_get_service:
        # Make the delete request with an invalid object type
        url = reverse('storage:delete_object', kwargs={
            'bucket_type': s3_test_paths['bucket_type'],
            'object_type': 'invalid_type',
            'object_path': s3_test_paths['file_path']
        })
        response = authenticated_client.post(url)
        
        # Should return a bad request response
        assert response.status_code == 400
        
        # Verify the service was not called
        mock_get_service.assert_not_called()


def test_delete_object_with_htmx(admin_user, s3_test_paths):
    """Test the response when requested via HTMX."""
    # Use RequestFactory to add HX-Request header
    factory = RequestFactory()
    url = reverse('storage:delete_object', kwargs={
        'bucket_type': s3_test_paths['bucket_type'],
        'object_type': 'file',
        'object_path': s3_test_paths['file_path']
    })
    request = factory.post(url, HTTP_HX_REQUEST='true')
    request.user = admin_user
    
    with patch('lacos.storage.views.file_operations_views.get_storage_service') as mock_get_service:
        # Mock the storage service
        mock_service = MagicMock()
        mock_service.delete_object.return_value = {'success': True}
        mock_get_service.return_value = mock_service
        
        response = delete_object(request, s3_test_paths['bucket_type'], 'file', s3_test_paths['file_path'])
    
    # Check the response format is suitable for HTMX
    assert response.status_code == 200
