import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from django.test import RequestFactory
from django.http import HttpResponse, JsonResponse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from lacos.storage.views.file_operations_views import delete_object, RenameObjectHTMXView


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
        
        # Add a mock authenticated user
        mock_user = MagicMock()
        mock_user.is_authenticated = True
        request.user = mock_user
        
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


@patch('lacos.storage.views.file_operations_views.BucketService')
@patch.object(RenameObjectHTMXView, 'render_bucket_content_template', return_value='rendered-html')
def test_rename_object_folder_success(mock_render_content, MockBucketService, prepared_request):
    request = prepared_request(
        '/storage/rename-object/bucket/folder/old/path/',
        method='post',
        htmx=True,
        data={'prompt': 'Renamed'}
    )

    mock_service = MockBucketService.return_value
    mock_service.rename_folder.return_value = {'success': True}

    response = RenameObjectHTMXView.as_view()(request, bucket_name='bucket', object_type='folder', object_path='old/path/')

    mock_service.rename_folder.assert_called_once_with('bucket', 'old/path/', 'Renamed')
    assert response.status_code == 200
    assert response.content.decode() == 'rendered-html'


@patch('lacos.storage.views.file_operations_views.BucketService')
@patch.object(RenameObjectHTMXView, 'render_bucket_content_template', return_value='rendered-html')
def test_rename_object_file_failure(mock_render_content, MockBucketService, prepared_request):
    request = prepared_request(
        '/storage/rename-object/bucket/file/folder/file.txt',
        method='post',
        htmx=True,
        data={'prompt': 'file.txt'}
    )

    mock_service = MockBucketService.return_value
    mock_service.rename_file.return_value = {'success': False, 'error': 'exists'}

    response = RenameObjectHTMXView.as_view()(request, bucket_name='bucket', object_type='file', object_path='folder/file.txt')

    mock_service.rename_file.assert_called_once_with('bucket', 'folder/file.txt', 'file.txt')
    assert response.status_code == 400
    assert 'exists' in response.content.decode()


    
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
    object_path = 'test-folder/'
    request = prepared_request(f'/storage/delete/{bucket_type}/{object_type}/{object_path}', method='post')

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
