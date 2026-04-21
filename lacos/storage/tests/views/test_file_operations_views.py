import pytest
import json
from unittest.mock import MagicMock, patch
from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from lacos.blam.models.collection.collection_repository import Collection
from lacos.users.models import CollectionManagerAssignment
from lacos.users.tests.factories import UserFactory
from lacos.storage.views.file_operations_views import (
    RenameObjectHTMXView,
    _fetch_markdown_html,
    delete_object,
)

pytestmark = pytest.mark.django_db


def _ensure_group(name: str) -> Group:
    return Group.objects.get_or_create(name=name)[0]


def _grant_collection_access(request, object_path: str):
    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))

    stripped_path = (object_path or "").strip("/")
    identifier = stripped_path.split("/", 1)[0] if stripped_path else None
    if identifier:
        collection, _ = Collection.objects.get_or_create(identifier=identifier)
        CollectionManagerAssignment.objects.get_or_create(user=user, collection=collection)

    request.user = user
    return user


@pytest.fixture
def prepared_request():
    """Factory for creating request objects with proper middleware."""
    def _create_request(path='/', method='get', htmx=False, **kwargs):
        factory = RequestFactory()
        
        if method.lower() == 'post':
            request = factory.post(path, **kwargs)
        else:
            request = factory.get(path, **kwargs)
        
        # Add session without saving to database
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save = lambda: None  # Mock the save method to do nothing
        
        # Add messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        # Add HTMX headers if needed
        if htmx:
            request.headers = {'HX-Request': 'true'}
        else:
            request.headers = {}

        request.user = UserFactory()
        
        return request
    
    return _create_request


@pytest.fixture
def mock_bucket_service():
    """Mock BucketService with expected properties and methods."""
    mock_service = MagicMock()
    mock_service.ingest_bucket = 'ingest-bucket'
    mock_service.production_bucket = 'production-bucket'
    
    # Set up list_bucket_contents to return test data
    mock_service.list_bucket_contents.return_value = [
        {'path': 'test-collection/file1.xml', 'is_dir': False},
        {'path': 'test-collection/subfolder', 'is_dir': True}
    ]
    
    # Set up get_root_level_items to return test structure
    mock_service.get_root_level_items.return_value = {
        'name': 'root',
        'children': [
            {'name': 'test-collection', 'path': 'test-collection', 'type': 'folder'}
        ]
    }
    
    return mock_service


@patch('lacos.storage.views.file_operations_views.get_token', return_value='csrf-token')
@patch('lacos.storage.views.file_operations_views.BucketService')
@patch.object(RenameObjectHTMXView, 'render_bucket_content_template', return_value='rendered-html')
def test_rename_object_folder_success(mock_render_content, MockBucketService, mock_get_token, prepared_request):
    object_path = 'old/old/'
    request = prepared_request(
        '/storage/rename-object/bucket/folder/old/path/',
        method='post',
        htmx=True,
        data={'newName': 'Renamed'}
    )
    _grant_collection_access(request, object_path)

    mock_service = MockBucketService.return_value
    mock_service.rename_folder.return_value = {'success': True}

    response = RenameObjectHTMXView.as_view()(request, bucket_name='bucket', object_type='folder', object_path=object_path)

    mock_service.rename_folder.assert_called_once_with('bucket', object_path, 'Renamed')
    assert response.status_code == 200
    content = response.content.decode()
    assert content.startswith('rendered-html')
    assert 'rename-object-modal-wrapper' in content


@patch('lacos.storage.views.file_operations_views.get_token', return_value='csrf-token')
@patch('lacos.storage.views.file_operations_views.BucketService')
@patch.object(RenameObjectHTMXView, 'render_bucket_content_template', return_value='rendered-html')
def test_rename_object_file_failure(mock_render_content, MockBucketService, mock_get_token, prepared_request):
    object_path = 'folder/file.txt'
    request = prepared_request(
        '/storage/rename-object/bucket/file/folder/file.txt',
        method='post',
        htmx=True,
        data={'newName': 'file.txt'}
    )
    _grant_collection_access(request, object_path)

    mock_service = MockBucketService.return_value
    mock_service.rename_file.return_value = {'success': False, 'error': 'exists'}

    response = RenameObjectHTMXView.as_view()(request, bucket_name='bucket', object_type='file', object_path=object_path)

    mock_service.rename_file.assert_called_once_with('bucket', object_path, 'file.txt')
    assert response.status_code == 400
    content = response.content.decode()
    assert 'exists' in content
    assert 'rename-object-modal-wrapper' in content


    
# Tests for delete_object view

@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_folder_success(mock_bucket_service, prepared_request):
    """Test successful deletion of a folder."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    # Configure necessary attributes on the mock instance
    mock_instance.ingest_bucket = 'test-ingest-bucket' 
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.delete_folder.return_value = {"success": True}

    # Create a POST request
    bucket_type = 'ingest'
    object_type = 'folder'
    object_path = 'test-folder/test-folder/'
    request = prepared_request(f'/storage/delete/{bucket_type}/{object_type}/{object_path}', method='post')
    _grant_collection_access(request, object_path)

    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)

    # Assert service was called correctly with the configured bucket name
    mock_instance.delete_folder.assert_called_once_with('test-ingest-bucket', object_path)

    # Check response is successful JSON
    assert response.status_code == 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is True
    assert "Successfully deleted" in response_data['message']


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_file_success(mock_bucket_service, prepared_request):
    """Test successful deletion of a file."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    # Configure necessary attributes on the mock instance
    mock_instance.ingest_bucket = 'test-ingest-bucket' 
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.delete_file.return_value = {"success": True}

    # Create a POST request
    bucket_type = 'production'
    object_type = 'file'
    object_path = 'test-folder/test.txt'
    request = prepared_request(f'/storage/delete/{bucket_type}/{object_type}/{object_path}', method='post')
    _grant_collection_access(request, object_path)

    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)

    # Assert service was called correctly with the configured bucket name
    mock_instance.delete_file.assert_called_once_with('test-production-bucket', object_path)

    # Check response is successful JSON
    assert response.status_code == 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is True
    assert "Successfully deleted" in response_data['message']


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_failure(mock_bucket_service, prepared_request):
    """Test failed deletion of an object."""
    # Configure mock service response for failure
    mock_instance = mock_bucket_service.return_value
    # Configure necessary attributes on the mock instance
    mock_instance.ingest_bucket = 'test-ingest-bucket' 
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.delete_file.return_value = {
        "success": False, 
        "error": "File not found"
    }

    # Create a POST request
    bucket_type = 'ingest'
    object_type = 'file'
    object_path = 'non-existent.txt'
    request = prepared_request(f'/storage/delete/{bucket_type}/{object_type}/{object_path}', method='post')
    _grant_collection_access(request, object_path)

    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)

    # Assert service was called correctly
    mock_instance.delete_file.assert_called_once_with('test-ingest-bucket', object_path)

    # Check response is error JSON
    assert response.status_code == 200  # JsonResponse defaults to 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is False
    assert "Failed to delete" in response_data['error']
    assert "File not found" in response_data['error']


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_exception(mock_bucket_service, prepared_request):
    """Test handling of exception during deletion operation."""
    # Configure mock service to raise an exception
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.delete_file.side_effect = Exception("Connection error")
    
    # Create a POST request with HTMX headers
    bucket_type = 'ingest'
    object_type = 'file'
    object_path = 'test.txt'
    request = prepared_request(
        f'/storage/delete-object/{bucket_type}/{object_type}/{object_path}', 
        method='post', 
        htmx=True
    )
    _grant_collection_access(request, object_path)
    
    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)
    
    # Assert service was called with correct parameters
    mock_instance.delete_file.assert_called_once_with('test-ingest-bucket', object_path)
    
    # Check error response for HTMX request
    assert response.status_code == 500
    assert "Connection error" in response.content.decode('utf-8')
    
    # Verify error message was added to the request
    messages = list(request._messages)
    assert len(messages) == 1
    assert "Error deleting file" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_method_not_allowed(mock_bucket_service, prepared_request):
    """Test that the view rejects non-POST requests."""
    # Create a GET request
    bucket_type = 'ingest'
    object_type = 'folder'
    object_path = 'test-folder/'
    request = prepared_request(
        f'/storage/delete-object/{bucket_type}/{object_type}/{object_path}', 
        method='get'
    )
    
    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)
    
    # Check response is a JSON error
    assert response.status_code == 200  # Django's JsonResponse defaults to 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is False
    assert response_data['error'] == 'Method not allowed'
    
    # Verify service methods were not called
    mock_instance = mock_bucket_service.return_value
    mock_instance.delete_folder.assert_not_called()
    mock_instance.delete_file.assert_not_called()


def test_fetch_markdown_html_sanitizes_active_content():
    mock_bucket_service = MagicMock()
    mock_bucket_service.get_file_content.return_value = {
        "content": b'[safe](https://example.com) [bad](javascript:alert(1)) <script>alert(1)</script>',
    }

    result = _fetch_markdown_html(mock_bucket_service, "bucket-a", "folder/readme.md")

    assert result["markdown_html"] is not None
    assert "javascript:" not in result["markdown_html"]
    assert "<script" not in result["markdown_html"]
