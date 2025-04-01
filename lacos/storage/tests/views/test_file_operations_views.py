import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from django.urls import reverse
from django.test import RequestFactory
from django.http import HttpResponse, JsonResponse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware

from lacos.storage.views.file_operations_views import move_to_production, delete_object


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
@patch('lacos.storage.views.file_operations_views.render')
@patch('lacos.storage.views.file_operations_views.redirect')
def test_move_to_production_success_with_ingestion(
    mock_redirect, mock_render, MockBucketService, 
    prepared_request, mock_bucket_service
):
    """Test successful move to production with ingestion trigger."""
    # Set up mocks
    MockBucketService.return_value = mock_bucket_service
    mock_bucket_service.direct_move_to_production.return_value = {'success': True}
    mock_render.return_value = HttpResponse('Success')
    
    # Create request
    request = prepared_request('/storage/move-to-production/test-collection/', 
                             method='post', htmx=True)
    
    # Mock the import and the process_s3_prefix function
    mock_process = MagicMock(return_value='fake-task-id')
    
    # Patch the modules that get imported inside the function
    with patch.dict('sys.modules', {
        'lacos.ingest.tasks': MagicMock(process_s3_prefix=mock_process)
    }):
        # Call the view
        response = move_to_production(request, 'test-collection')
    
    # Verify bucket service calls
    mock_bucket_service.list_bucket_contents.assert_any_call('ingest-bucket', 'test-collection')
    mock_bucket_service.direct_move_to_production.assert_called_once_with('test-collection')
    
    # Verify ingestion was triggered
    mock_process.assert_called_once_with(
        bucket='production-bucket',
        prefix='test-collection/'
    )
    
    # Verify render was called for HTMX request
    mock_render.assert_called_once()
    
    # Verify we didn't redirect (since it was an HTMX request)
    mock_redirect.assert_not_called()
    
    # Verify response
    assert response.status_code == 200


@patch('lacos.storage.views.file_operations_views.BucketService')
@patch('lacos.storage.views.file_operations_views.render')
@patch('lacos.storage.views.file_operations_views.redirect')
def test_move_to_production_success_regular_request(
    mock_redirect, mock_render, MockBucketService, 
    prepared_request, mock_bucket_service
):
    """Test successful move to production with regular (non-HTMX) request."""
    # Set up mocks
    MockBucketService.return_value = mock_bucket_service
    mock_bucket_service.direct_move_to_production.return_value = {'success': True}
    mock_redirect.return_value = HttpResponse('Redirected')
    
    # Create request (no HTMX header)
    request = prepared_request('/storage/move-to-production/test-collection/', 
                             method='post', htmx=False)
    
    # Mock the import and the process_s3_prefix function
    mock_process = MagicMock(return_value='fake-task-id')
    
    # Patch the modules that get imported inside the function
    with patch.dict('sys.modules', {
        'lacos.ingest.tasks': MagicMock(process_s3_prefix=mock_process)
    }):
        # Call the view
        move_to_production(request, 'test-collection')
    
    # Verify ingestion was triggered
    mock_process.assert_called_once()
    
    # Verify we redirected for non-HTMX request
    mock_redirect.assert_called_once()
    
    # Verify render was not called for redirects
    mock_render.assert_not_called()


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_failed_move(
    MockBucketService, prepared_request, mock_bucket_service
):
    """Test failed move to production."""
    # Set up mocks
    MockBucketService.return_value = mock_bucket_service
    # Simulate failed move
    mock_bucket_service.direct_move_to_production.return_value = {
        'success': False, 
        'error': 'Test error'
    }
    
    # Create request
    request = prepared_request('/storage/move-to-production/test-collection/', 
                             method='post', htmx=True)
    
    # Create a mock for process_s3_prefix but it should never be called
    mock_process = MagicMock()
    
    # Patch the modules that get imported inside the function
    with patch.dict('sys.modules', {
        'lacos.ingest.tasks': MagicMock(process_s3_prefix=mock_process)
    }):
        # Call the view
        response = move_to_production(request, 'test-collection')
    
    # Verify ingestion was NOT triggered
    mock_process.assert_not_called()
    
    # Verify error response
    assert response.status_code == 400
    assert 'Test error' in response.content.decode()


@patch('lacos.storage.views.file_operations_views.BucketService')
@patch('lacos.storage.views.file_operations_views.render')
def test_move_to_production_success_ingestion_failure(
    mock_render, MockBucketService, prepared_request, mock_bucket_service
):
    """Test successful move but failed ingestion."""
    # Set up mocks
    MockBucketService.return_value = mock_bucket_service
    mock_bucket_service.direct_move_to_production.return_value = {'success': True}
    mock_render.return_value = HttpResponse('Success')
    
    # Create request
    request = prepared_request('/storage/move-to-production/test-collection/', 
                             method='post', htmx=True)
    
    # Mock the import but make process_s3_prefix raise an exception
    mock_process = MagicMock(side_effect=Exception('Ingestion error'))
    
    # Patch the modules that get imported inside the function
    with patch.dict('sys.modules', {
        'lacos.ingest.tasks': MagicMock(process_s3_prefix=mock_process)
    }):
        # Call the view
        response = move_to_production(request, 'test-collection')
    
    # Verify ingestion was attempted
    mock_process.assert_called_once()
    
    # Verify move was still successful
    assert response.status_code == 200
    
    # Verify that at least one warning message was added
    messages = [m.message for m in request._messages]
    assert any('failed to trigger ingestion' in str(m).lower() for m in messages)


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_method_not_allowed(
    MockBucketService, prepared_request
):
    """Test GET request is rejected."""
    # Create GET request
    request = prepared_request('/storage/move-to-production/test-collection/', 
                             method='get')
    
    # Call the view
    response = move_to_production(request, 'test-collection')
    
    # Verify response is a JsonResponse with the expected data
    assert isinstance(response, JsonResponse)
    
    # Parse the JSON content
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is False
    assert 'Method not allowed' in response_data['error']


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