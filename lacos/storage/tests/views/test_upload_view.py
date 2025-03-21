import pytest
import json
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.backends.base import SessionBase

from lacos.storage.views.upload_view import (
    upload_form,
    get_presigned_urls,
    mark_uploads_complete,
    copy_object_to_production
)


@pytest.fixture
def request_factory():
    """Fixture for a request factory."""
    return RequestFactory()


@pytest.fixture
def auth_user():
    """Fixture for an authenticated user."""
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.id = 1
    user.username = "testuser"
    return user


@pytest.fixture
def prepared_request(request_factory, auth_user):
    """Fixture for preparing a request with user, session, and optional HTMX headers."""
    def _prepare_request(request_path, method='post', data=None, htmx=False, content_type=None):
        data = data or {}
        
        if method.lower() == 'get':
            request = request_factory.get(request_path)
        else:
            # Set the Content-Type for POST requests
            if content_type == 'application/json':
                # For JSON content, use json parameter
                request = request_factory.post(
                    request_path, 
                    data=json.dumps(data), 
                    content_type='application/json'
                )
                # For views that expect to parse JSON from request.body
                setattr(request, '_body', json.dumps(data).encode('utf-8'))
            else:
                # For form data, use data parameter
                request = request_factory.post(
                    request_path, 
                    data=data,
                    content_type='application/x-www-form-urlencoded'
                )
        
        # Set user
        request.user = auth_user
        
        # Set scheme and host
        type(request).scheme = PropertyMock(return_value='http')
        request.get_host = MagicMock(return_value='testserver')
        
        # Add session
        mock_session = MagicMock(spec=SessionBase)
        mock_session.session_key = "test_session_key"
        mock_session._session = {}
        mock_session.modified = False
        request.session = mock_session
        
        # Add messages storage
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        # Add HTMX header if needed
        if htmx:
            request.headers = {'HX-Request': 'true'}
        else:
            request.headers = {}
        
        # Add META for cookie handling
        request.META = {'HTTP_COOKIE': 'sessionid=test_session_key'}
        if hasattr(request, 'content_type') and request.content_type:
            request.META['CONTENT_TYPE'] = request.content_type
        
        return request
    
    return _prepare_request


@patch('lacos.storage.views.upload_view.render')
def test_upload_form(mock_render, prepared_request):
    """Test the upload form view."""
    request = prepared_request('/storage/upload/', method='get')
    upload_form(request)
    mock_render.assert_called_once_with(request, "upload/upload_form.html")


@patch('lacos.storage.views.upload_view.UploadService')
@patch('lacos.storage.views.upload_view.render')
def test_get_presigned_urls(mock_render, mock_upload_service, prepared_request):
    """Test presigned URL generation."""
    # Configure mock service response
    mock_instance = mock_upload_service.return_value
    mock_instance.generate_batch_presigned_posts.return_value = {
        "success": True,
        "presigned_posts": [{"success": True, "file_name": "test.jpg"}],
        "total_urls": 1,
        "total_failures": 0
    }
    
    # Create request with form data directly
    files_metadata = json.dumps([{"file_name": "test.jpg", "file_type": "image/jpeg"}])
    request = prepared_request(
        '/storage/upload/presigned-urls/',
        method='post',
        data={'folder_name': 'test-folder', 'files_metadata': files_metadata}
    )
    
    # Ensure the form data is directly available in request.POST
    from django.http.request import QueryDict
    request.POST = QueryDict('', mutable=True)
    request.POST.update({'folder_name': 'test-folder', 'files_metadata': files_metadata})
    
    # Call the view
    response = get_presigned_urls(request)
    
    # Assert service was called with correct parameters
    mock_instance.generate_batch_presigned_posts.assert_called_once()
    args, kwargs = mock_instance.generate_batch_presigned_posts.call_args
    assert kwargs['path_prefix'] == 'test-folder'
    assert kwargs['expiration'] == 3600
    assert isinstance(kwargs['files_metadata'], list)
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is True


@patch('lacos.storage.views.upload_view.UploadService')
def test_mark_uploads_complete(mock_upload_service, prepared_request):
    """Test marking uploads as complete."""
    # Configure mock service responses
    mock_instance = mock_upload_service.return_value
    mock_instance.mark_upload_complete.side_effect = [
        {"success": True, "exists": True, "s3_key": "folder/test.jpg"},
        {"success": True, "exists": True, "s3_key": "folder/test2.jpg"}
    ]
    
    # Create request with S3 keys to verify - this function expects JSON in request.body
    json_data = {"s3_keys": ["folder/test.jpg", "folder/test2.jpg"]}
    request = prepared_request(
        '/storage/upload/complete/',
        method='post',
        data=json_data,
        content_type='application/json'
    )
    
    # Call the view
    response = mark_uploads_complete(request)
    
    # Check service was called correctly
    assert mock_instance.mark_upload_complete.call_count == 2
    
    # Check first service call
    mock_instance.mark_upload_complete.assert_any_call("folder/test.jpg")
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is True
    assert response_data['total_verified'] == 2


@patch('lacos.storage.views.upload_view.UploadService')
def test_copy_object_to_production(mock_upload_service, prepared_request):
    """Test copying object to production."""
    # Configure mock service response
    mock_instance = mock_upload_service.return_value
    mock_instance.copy_object.return_value = {
        "success": True,
        "source_key": "source/test.jpg",
        "dest_key": "dest/test.jpg"
    }
    
    # Create request
    request = prepared_request(
        '/storage/copy-to-production/',
        method='post',
        data={'source_key': 'source/test.jpg', 'dest_key': 'dest/test.jpg'}
    )
    
    # Ensure the form data is directly available in request.POST
    from django.http.request import QueryDict
    request.POST = QueryDict('', mutable=True)
    request.POST.update({'source_key': 'source/test.jpg', 'dest_key': 'dest/test.jpg'})
    
    # Call the view
    response = copy_object_to_production(request)
    
    # Check service was called with correct parameters
    mock_instance.copy_object.assert_called_once()
    args, kwargs = mock_instance.copy_object.call_args
    assert kwargs['source_key'] == 'source/test.jpg'
    assert kwargs['dest_key'] == 'dest/test.jpg'
    assert kwargs['source_bucket'] is None
    assert kwargs['dest_bucket'] is None
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is True


@patch('lacos.storage.views.upload_view.UploadService')
def test_copy_object_missing_source_key(mock_upload_service, prepared_request):
    """Test response when source key is missing."""
    # Create request without source key
    request = prepared_request(
        '/storage/copy-to-production/',
        method='post',
        data={}
    )
    
    # Ensure the form data is directly available as an empty request.POST
    from django.http.request import QueryDict
    request.POST = QueryDict('', mutable=True)
    
    # Call the view
    response = copy_object_to_production(request)
    
    # Service should not be called
    mock_upload_service.return_value.copy_object.assert_not_called()
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is False
    assert "Source key is required" in response_data['error']


@patch('lacos.storage.views.upload_view.UploadService')
def test_service_error_handling(mock_upload_service, prepared_request):
    """Test handling of service errors."""
    # Configure mock service to raise an exception
    mock_instance = mock_upload_service.return_value
    mock_instance.copy_object.side_effect = Exception("Service error")
    
    # Create request
    request = prepared_request(
        '/storage/copy-to-production/',
        method='post',
        data={'source_key': 'test.jpg'}
    )
    
    # Ensure the form data is directly available in request.POST
    from django.http.request import QueryDict
    request.POST = QueryDict('', mutable=True)
    request.POST.update({'source_key': 'test.jpg'})
    
    # Call the view
    response = copy_object_to_production(request)
    
    # Check service was called
    mock_instance.copy_object.assert_called_once()
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is False
    assert "Service error" in response_data['error']


