import pytest
from unittest.mock import patch, MagicMock

from lacos.storage.views.dashboard_views import (
    archivist_dashboard,
    load_folder_contents,
    RenameBucketHTMXView,
    RenameBucketModalHTMXView,
    RenameObjectModalHTMXView,
)

# Note: fixtures are now imported from conftest.py automatically

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_success(mock_render, mock_bucket_service, prepared_request):
    """Test successful loading of the archivist dashboard with root items."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = ['test-production-bucket']

    bucket_structures = {
        'test-ingest-bucket': {
            "type": "folder",
            "name": "test-ingest-bucket",
            "path": "",
            "children": [
                {"type": "folder", "name": "folder1", "path": "folder1/"},
                {"type": "file", "name": "test.jpg", "path": "test.jpg"}
            ]
        },
        'test-production-bucket': {
            "type": "folder",
            "name": "test-production-bucket",
            "path": "",
            "children": [
                {"type": "folder", "name": "folder2", "path": "folder2/"},
                {"type": "file", "name": "prod.jpg", "path": "prod.jpg"}
            ]
        }
    }

    def mock_get_root_items(bucket_name):
        return bucket_structures[bucket_name]

    mock_instance.get_root_level_items.side_effect = mock_get_root_items
    
    # Create request with success message
    request = prepared_request('/storage/dashboard/', method='get', data={'message': 'Test message'})
    
    # Call the view
    archivist_dashboard(request)
    
    # Assert service was called with correct parameters
    # The view now calls get_root_level_items for each accessible bucket
    assert mock_instance.get_root_level_items.call_count == 2
    
    # Check that the correct template was rendered with the right context
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/archivist_dashboard.html"
    assert 'ingest_structure' in context
    assert 'production_structure' in context
    assert 'message' in context
    assert context['message'] == 'Test message'
    
    # Verify the structure of the context data
    ingest_structure = context['ingest_structure']
    assert ingest_structure['type'] == 'folder'
    assert ingest_structure['name'] == 'test-ingest-bucket'
    assert len(ingest_structure['children']) == 2
    
    production_structure = context['production_structure']
    assert production_structure['type'] == 'folder'
    assert production_structure['name'] == 'test-production-bucket'
    assert len(production_structure['children']) == 2

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_empty_buckets(mock_render, mock_bucket_service, prepared_request):
    """Test dashboard loading with empty buckets."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = []

    bucket_structures = {
        'test-ingest-bucket': {"type": "folder", "name": "test-ingest-bucket", "path": "", "children": []},
        'test-production-bucket': {"type": "folder", "name": "test-production-bucket", "path": "", "children": []}
    }

    def mock_get_root_items(bucket_name):
        return bucket_structures[bucket_name]

    mock_instance.get_root_level_items.side_effect = mock_get_root_items
    
    request = prepared_request('/storage/dashboard/')
    archivist_dashboard(request)
    
    # Verify empty structures are handled correctly
    context = mock_render.call_args[0][2]
    assert len(context['ingest_structure']['children']) == 0
    assert len(context['production_structure']['children']) == 0

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_error_handling(mock_render, mock_bucket_service, prepared_request):
    """Test dashboard error handling when bucket service fails."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = []
    mock_instance.get_root_level_items.side_effect = Exception("Service error")
    
    request = prepared_request('/storage/dashboard/')
    archivist_dashboard(request)
    
    # Verify empty structures are returned on error
    context = mock_render.call_args[0][2]
    assert len(context['ingest_structure']['children']) == 0
    assert len(context['production_structure']['children']) == 0

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_ingest_bucket(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of a folder in the ingest bucket."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_folder_contents.return_value = [
        {"type": "folder", "name": "subfolder", "path": "folder1/subfolder/"},
        {"type": "file", "name": "test.txt", "path": "folder1/test.txt"}
    ]
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/folder1/')
    load_folder_contents(request, 'ingest', 'folder1/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with('test-ingest-bucket', 'folder1/')
    
    # Verify template rendering
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/folder_contents_partial.html"
    assert context['bucket_type'] == 'ingest'
    assert context['folder_path'] == 'folder1/'
    assert len(context['folder_contents']) == 2

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_production_bucket(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of a folder in the production bucket."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_folder_contents.return_value = [
        {"type": "file", "name": "prod.txt", "path": "folder2/prod.txt"}
    ]
    
    request = prepared_request('/storage/dashboard/folder-contents/production/folder2/')
    load_folder_contents(request, 'production', 'folder2/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with('test-production-bucket', 'folder2/')
    
    # Verify template rendering
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/folder_contents_partial.html"
    assert context['bucket_type'] == 'production'
    assert context['folder_path'] == 'folder2/'
    assert len(context['folder_contents']) == 1

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_empty_folder(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of an empty folder."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_folder_contents.return_value = []
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/empty_folder/')
    load_folder_contents(request, 'ingest', 'empty_folder/')
    
    # Verify template rendering with empty contents
    mock_render.assert_called_once()
    context = mock_render.call_args[0][2]
    assert len(context['folder_contents']) == 0


@patch('lacos.storage.views.dashboard_views.get_token', return_value='csrf-token')
@patch('lacos.storage.views.dashboard_views.BucketService')
@patch.object(RenameBucketHTMXView, 'render_bucket_content_template', return_value='bucket-html')
@patch.object(RenameBucketHTMXView, 'build_bucket_tabs_oob_response', return_value='combined-html')
def test_rename_bucket_htmx_success(mock_build, mock_render_content, MockBucketService, mock_get_token, prepared_request):
    mock_service = MockBucketService.return_value
    mock_service.rename_bucket.return_value = {
        'success': True,
        'message': 'renamed',
        'bucket_name': 'new-bucket'
    }

    request = prepared_request('/storage/htmx/rename-bucket/old-bucket/', method='post', htmx=True, data={'newName': 'new-bucket'})

    response = RenameBucketHTMXView.as_view()(request, bucket_name='old-bucket')

    mock_service.rename_bucket.assert_called_once_with('old-bucket', 'new-bucket')
    mock_render_content.assert_called_once()
    assert response.status_code == 200
    content = response.content.decode()
    assert content.startswith('combined-html')
    assert 'rename-bucket-modal-wrapper' in content
    assert 'hx-swap-oob="outerHTML"' in content


@patch('lacos.storage.views.dashboard_views.get_token', return_value='csrf-token')
@patch('lacos.storage.views.dashboard_views.BucketService')
@patch.object(RenameBucketHTMXView, 'render_bucket_content_template', return_value='bucket-html')
def test_rename_bucket_htmx_failure(mock_render_content, MockBucketService, mock_get_token, prepared_request):
    mock_service = MockBucketService.return_value
    mock_service.rename_bucket.return_value = {'success': False, 'error': 'Conflict'}

    request = prepared_request('/storage/htmx/rename-bucket/old/', method='post', htmx=True, data={'newName': 'exists'})

    response = RenameBucketHTMXView.as_view()(request, bucket_name='old')

    assert response.status_code == 400
    mock_render_content.assert_not_called()
    content = response.content.decode()
    assert 'Conflict' in content
    assert 'rename-bucket-modal-wrapper' in content


@patch('lacos.storage.views.dashboard_views.get_token', return_value='csrf-token')
def test_rename_bucket_modal_htmx(mock_get_token, prepared_request):
    request = prepared_request('/storage/htmx/rename-bucket-modal/demo/', method='get', htmx=True)
    response = RenameBucketModalHTMXView.as_view()(request, bucket_name='demo')
    assert response.status_code == 200
    content = response.content.decode()
    assert 'rename-bucket-modal-wrapper' in content
    assert 'demo' in content


@patch('lacos.storage.views.dashboard_views.get_token', return_value='csrf-token')
def test_rename_object_modal_htmx(mock_get_token, prepared_request):
    request = prepared_request('/storage/htmx/rename-object-modal/bucket/folder/path/to/item/', method='get', htmx=True)
    response = RenameObjectModalHTMXView.as_view()(request, bucket_name='bucket', object_type='folder', object_path='path/to/item/')
    assert response.status_code == 200
    content = response.content.decode()
    assert 'rename-object-modal-wrapper' in content
    assert 'item' in content

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_error_handling(mock_render, mock_bucket_service, prepared_request):
    """Test error handling when loading folder contents fails."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_folder_contents.side_effect = Exception("Service error")
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/error_folder/')
    load_folder_contents(request, 'ingest', 'error_folder/')
    
    # Verify empty list is returned on error
    mock_render.assert_called_once()
    context = mock_render.call_args[0][2]
    assert len(context['folder_contents']) == 0
