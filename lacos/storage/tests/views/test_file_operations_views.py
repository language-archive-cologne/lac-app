import pytest
import json
from unittest.mock import patch, MagicMock
from django.urls import reverse

from lacos.storage.views.file_operations_views import move_to_production, delete_object


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_success(mock_bucket_service, prepared_request):
    """Test successful move to production operation using the direct_move_to_production method."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.direct_move_to_production.return_value = {
        "success": True,
        "message": "Successfully moved folder 'test-collection/' to production bucket (5 files copied)"
    }
    
    # Create a POST request
    folder_path = 'test-collection/'
    request = prepared_request(f'/storage/move-to-production/{folder_path}', method='post')
    
    # Mock the reverse function
    with patch('lacos.storage.views.file_operations_views.reverse') as mock_reverse:
        mock_reverse.return_value = '/storage/dashboard/'
        
        # Call the view
        response = move_to_production(request, folder_path)
        
        # Assert service was called with correct parameters
        mock_instance.direct_move_to_production.assert_called_once_with(folder_path)
        
        # Check response is a redirect to dashboard
        assert response.status_code == 302
        assert response.url.startswith('/storage/dashboard/')
        
        # Verify message was added to the request
        messages = list(request._messages)
        assert len(messages) == 1
        assert "Successfully moved folder" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_failure(mock_bucket_service, prepared_request):
    """Test handling of failed move to production operation."""
    # Configure mock service response for failure
    mock_instance = mock_bucket_service.return_value
    mock_instance.direct_move_to_production.return_value = {
        "success": False,
        "error": "Error: Ingest and production buckets must be different"
    }
    
    # Create a POST request
    folder_path = 'test-collection/'
    request = prepared_request(f'/storage/move-to-production/{folder_path}', method='post')
    
    # Mock the reverse function
    with patch('lacos.storage.views.file_operations_views.reverse') as mock_reverse:
        mock_reverse.return_value = '/storage/dashboard/'
        
        # Call the view
        response = move_to_production(request, folder_path)
        
        # Check response is a redirect to dashboard
        assert response.status_code == 302
        assert response.url == '/storage/dashboard/'
        
        # Verify error message was added to the request
        messages = list(request._messages)
        assert len(messages) == 1
        assert "Failed to move folder" in str(messages[0])
        assert "Error: Ingest and production buckets must be different" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_exception(mock_bucket_service, prepared_request):
    """Test handling of exception during move to production operation."""
    # Configure mock service to raise an exception
    mock_instance = mock_bucket_service.return_value
    mock_instance.direct_move_to_production.side_effect = Exception("Connection error")
    
    # Create a POST request
    folder_path = 'test-collection/'
    request = prepared_request(f'/storage/move-to-production/{folder_path}', method='post')
    
    # Mock the reverse function
    with patch('lacos.storage.views.file_operations_views.reverse') as mock_reverse:
        mock_reverse.return_value = '/storage/dashboard/'
        
        # Call the view
        response = move_to_production(request, folder_path)
        
        # Check response is a redirect to dashboard
        assert response.status_code == 302
        assert response.url == '/storage/dashboard/'
        
        # Verify error message was added to the request
        messages = list(request._messages)
        assert len(messages) == 1
        assert "Error moving folder to production" in str(messages[0])
        assert "Connection error" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_move_to_production_method_not_allowed(mock_bucket_service, prepared_request):
    """Test that the view rejects non-POST requests."""
    # Create a GET request
    folder_path = 'test-collection/'
    request = prepared_request(f'/storage/move-to-production/{folder_path}', method='get')
    
    # Call the view
    response = move_to_production(request, folder_path)
    
    # Check response is a JSON error
    assert response.status_code == 200  # Django's JsonResponse defaults to 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is False
    assert response_data['error'] == 'Method not allowed'
    
    # Verify service was not called
    mock_instance = mock_bucket_service.return_value
    mock_instance.direct_move_to_production.assert_not_called()


# Tests for delete_object view

@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_folder_success(mock_bucket_service, prepared_request):
    """Test successful deletion of a folder."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.delete_folder.return_value = {
        "success": True,
        "message": "Successfully deleted directory test-folder/ with 3 objects",
        "deleted_objects": 3
    }
    
    # Create a POST request with HTMX headers
    bucket_type = 'ingest'
    object_type = 'folder'
    object_path = 'test-folder/'
    request = prepared_request(
        f'/storage/delete-object/{bucket_type}/{object_type}/{object_path}', 
        method='post', 
        htmx=True
    )
    
    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)
    
    # Assert service was called with correct parameters
    mock_instance.delete_folder.assert_called_once_with('test-ingest-bucket', object_path)
    
    # Check response for HTMX request
    assert response.status_code == 200
    assert response.content.decode('utf-8') == ""  # Empty response for htmx
    
    # Verify message was added to the request
    messages = list(request._messages)
    assert len(messages) == 1
    assert "Successfully deleted folder" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_file_success(mock_bucket_service, prepared_request):
    """Test successful deletion of a file."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.delete_file.return_value = {
        "success": True,
        "message": "Successfully deleted object test.txt",
        "deleted_objects": 1
    }
    
    # Create a POST request (non-HTMX)
    bucket_type = 'production'
    object_type = 'file'
    object_path = 'test.txt'
    request = prepared_request(
        f'/storage/delete-object/{bucket_type}/{object_type}/{object_path}', 
        method='post'
    )
    
    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)
    
    # Assert service was called with correct parameters
    mock_instance.delete_file.assert_called_once_with('test-production-bucket', object_path)
    
    # Check JSON response for non-HTMX request
    assert response.status_code == 200
    response_data = json.loads(response.content.decode('utf-8'))
    assert response_data['success'] is True
    assert "Successfully deleted" in response_data['message']
    
    # Verify message was added to the request
    messages = list(request._messages)
    assert len(messages) == 1
    assert "Successfully deleted file" in str(messages[0])


@patch('lacos.storage.views.file_operations_views.BucketService')
def test_delete_object_failure(mock_bucket_service, prepared_request):
    """Test handling of failed deletion operation."""
    # Configure mock service response for failure
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.delete_folder.return_value = {
        "success": False,
        "error": "Access denied or object doesn't exist"
    }
    
    # Create a POST request with HTMX headers
    bucket_type = 'ingest'
    object_type = 'folder'
    object_path = 'nonexistent-folder/'
    request = prepared_request(
        f'/storage/delete-object/{bucket_type}/{object_type}/{object_path}', 
        method='post', 
        htmx=True
    )
    
    # Call the view
    response = delete_object(request, bucket_type, object_type, object_path)
    
    # Assert service was called with correct parameters
    mock_instance.delete_folder.assert_called_once_with('test-ingest-bucket', object_path)
    
    # Check error response for HTMX request
    assert response.status_code == 400
    assert "Access denied" in response.content.decode('utf-8')
    
    # Verify error message was added to the request
    messages = list(request._messages)
    assert len(messages) == 1
    assert "Failed to delete folder" in str(messages[0])


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