import pytest
from unittest.mock import patch

from lacos.storage.views.dashboard_views import archivist_dashboard

# Note: fixtures are now imported from conftest.py automatically

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard(mock_render, mock_bucket_service, prepared_request):
    """Test the archivist dashboard view."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_folder_structure.side_effect = [
        # Mock response for ingest bucket
        {
            'folders': [{'name': 'folder1', 'path': 'folder1/'}],
            'files': [{'name': 'test.jpg', 'path': 'test.jpg'}]
        },
        # Mock response for production bucket
        {
            'folders': [{'name': 'folder2', 'path': 'folder2/'}],
            'files': [{'name': 'prod.jpg', 'path': 'prod.jpg'}]
        }
    ]
    
    # Create request
    request = prepared_request('/storage/dashboard/', method='get', data={'message': 'Test message'})
    
    # Call the view
    archivist_dashboard(request)
    
    # Assert service was called with correct parameters
    mock_instance.get_folder_structure.assert_any_call('test-ingest-bucket')
    mock_instance.get_folder_structure.assert_any_call('test-production-bucket')
    
    # Check that the correct template was rendered with the right context
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/archivist_dashboard.html"
    assert 'ingest_structure' in context
    assert 'production_structure' in context
    assert 'message' in context
    assert context['message'] == 'Test message'