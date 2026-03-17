import pytest
import json
from unittest.mock import patch
from django.http.request import QueryDict
from unittest.mock import MagicMock

# Import the actual service class for the spec
from lacos.storage.services.upload_service import UploadService

from lacos.storage.views.presigned_url_views import (
    get_presigned_urls,
    mark_uploads_complete
)

# Note: fixtures are now imported from conftest.py automatically

@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
def test_get_presigned_urls(mock_get_upload_service, _mock_ensure_collection_access, prepared_request):
    """Test presigned URL generation."""
    # Configure mock service response
    mock_instance = mock_get_upload_service.return_value
    mock_instance.generate_batch_presigned_posts.return_value = {
        "success": True,
        "presigned_posts": [{"success": True, "file_name": "test.jpg", "s3_key": "test-folder/test.jpg"}],
        "total_urls": 1,
        "total_failures": 0
    }
    
    # Create request with form data directly
    files_metadata = json.dumps([{"file_name": "test.jpg", "file_type": "image/jpeg"}])
    request = prepared_request(
        '/storage/presigned-urls/',
        method='post',
        data={'folder_name': 'test-folder', 'files_metadata': files_metadata}
    )
    
    # Ensure the form data is directly available in request.POST
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

@pytest.fixture
def mock_upload_service_instance():
    """Creates a configured mock instance of UploadService."""
    mock_instance = MagicMock(spec=UploadService) # Use spec for better mocking
    
    # Define the mock return values that will be returned by mark_upload_complete
    mock_return_values = [
        {
            "success": True, 
            "exists": True, 
            "s3_key": "folder/test.jpg",
            "file_size": 1024,
            "file_size_formatted": "1.00 KB",
            "content_type": "image/jpeg",
            "last_modified": "2023-01-01T00:00:00"
        },
        {
            "success": True, 
            "exists": True, 
            "s3_key": "folder/test2.jpg",
            "file_size": 2048,
            "file_size_formatted": "2.00 KB",
            "content_type": "image/jpeg",
            "last_modified": "2023-01-01T00:00:00"
        }
    ]
    
    # Set up the side_effect to return the predefined values
    mock_instance.mark_upload_complete.side_effect = mock_return_values
    
    # Ensure _format_size returns a string instead of a MagicMock
    mock_instance._format_size.return_value = "3.00 KB"
    
    # Add bucket name attribute needed by the view logic
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    
    return mock_instance

@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
def test_mark_uploads_complete(
    mock_get_upload_service,
    _mock_ensure_collection_access,
    prepared_request,
    mock_upload_service_instance,
):
    """Test marking uploads as complete."""
    # Configure the mocked getter to return our specific instance
    mock_get_upload_service.return_value = mock_upload_service_instance
    
    # Create request with S3 keys to verify - this function expects JSON in request.body
    json_data = {"s3_keys": ["folder/test.jpg", "folder/test2.jpg"]}
    request = prepared_request(
        '/storage/mark-uploads-complete/',
        method='post',
        data=json_data,
        content_type='application/json'
    )
    
    # Ensure the request has a properly formatted body
    request._body = json.dumps(json_data).encode('utf-8')
    
    # Call the view (which will now use get_upload_service)
    response = mark_uploads_complete(request)
    
    # Check service method was called correctly on our instance
    assert mock_upload_service_instance.mark_upload_complete.call_count == 2
    
    # Check service calls
    mock_upload_service_instance.mark_upload_complete.assert_any_call("folder/test.jpg", bucket_name=None)
    mock_upload_service_instance.mark_upload_complete.assert_any_call("folder/test2.jpg", bucket_name=None)
    
    # Check response
    response_data = json.loads(response.content)
    assert response.status_code == 200
    assert response_data['success'] is True
    assert response_data['total_verified'] == 2
    assert response_data['total_size'] == 3072  # 1024 + 2048
    assert response_data['total_size_formatted'] == "3.00 KB" 
