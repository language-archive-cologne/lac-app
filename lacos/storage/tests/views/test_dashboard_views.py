import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse

from lacos.storage.views.dashboard_views import (
    archivist_dashboard,
    load_folder_contents,
    RenameBucketHTMXView,
    RenameBucketModalHTMXView,
    RenameObjectModalHTMXView,
)
from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin

# Note: fixtures are now imported from conftest.py automatically

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_success(mock_render, mock_bucket_service, prepared_request):
    """Test successful loading of the archivist dashboard with root items."""
    # Configure mock service response
    mock_instance = mock_bucket_service.return_value
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.bucket_cache_metadata = {"source": "refresh", "duration": 0.05, "expires_in": 15}
    mock_instance.ocfl_buckets = ['test-production-bucket']

    # Create request with success message
    request = prepared_request('/storage/dashboard/', method='get', data={'message': 'Test message'})
    
    # Call the view
    archivist_dashboard(request)
    mock_instance.get_all_accessible_buckets.assert_called_with(force_refresh=False, raise_on_error=True)
    
    # The dashboard should not eagerly fetch bucket structures anymore
    mock_instance.get_root_level_items.assert_not_called()
    
    # Check that the correct template was rendered with the right context
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/archivist_dashboard.html"
    assert 'message' in context
    assert context['message'] == 'Test message'
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['workspace_buckets'] == ['test-ingest-bucket', 'test-production-bucket']
    assert context['auto_load_url'] == reverse('storage:bucket_content_htmx', args=['test-ingest-bucket'])
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_empty_buckets(mock_render, mock_bucket_service, prepared_request):
    """Test dashboard loading with empty buckets."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.bucket_cache_metadata = {"source": "refresh", "duration": 0.05, "expires_in": 15}
    mock_instance.ocfl_buckets = []
    
    request = prepared_request('/storage/dashboard/')
    archivist_dashboard(request)
    mock_instance.get_all_accessible_buckets.assert_called_with(force_refresh=False, raise_on_error=True)
    
    context = mock_render.call_args[0][2]
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['workspace_buckets'] == ['test-ingest-bucket', 'test-production-bucket']
    assert context['auto_load_url'] == reverse('storage:bucket_content_htmx', args=['test-ingest-bucket'])
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_error_handling(mock_render, mock_bucket_service, prepared_request):
    """Test dashboard error handling when bucket service fails."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.bucket_cache_metadata = {"source": "refresh", "duration": 0.05, "expires_in": 15}
    mock_instance.ocfl_buckets = []

    request = prepared_request('/storage/dashboard/')
    archivist_dashboard(request)
    mock_instance.get_all_accessible_buckets.assert_called_with(force_refresh=False, raise_on_error=True)
    
    # Verify empty structures are returned on error
    context = mock_render.call_args[0][2]
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['workspace_buckets'] == ['test-ingest-bucket', 'test-production-bucket']
    assert context['auto_load_url'] == reverse('storage:bucket_content_htmx', args=['test-ingest-bucket'])


@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_force_fresh_adds_query(mock_render, mock_bucket_service, prepared_request):
    mock_instance = mock_bucket_service.return_value
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket']
    mock_instance.bucket_cache_metadata = {"source": "refresh", "duration": 0.05, "expires_in": 15}
    mock_instance.ocfl_buckets = []

    request = prepared_request('/storage/dashboard/?force_fresh=true')
    archivist_dashboard(request)
    mock_instance.get_all_accessible_buckets.assert_called_with(force_refresh=True, raise_on_error=True)

    context = mock_render.call_args[0][2]
    expected = reverse('storage:bucket_content_htmx', args=['test-ingest-bucket']) + '?force_fresh=true'
    assert context['auto_load_url'] == expected
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'


class _DummyHelperView(HtmxTemplateHelperMixin):
    """Simple helper to expose the mixin for testing."""


def test_build_bucket_tabs_oob_response_adds_hidden_input(request_factory):
    request = request_factory.get('/storage/test')
    request.session = {'storage_active_bucket': 'bucket-1'}

    view = _DummyHelperView()

    with patch.object(
        _DummyHelperView,
        'render_bucket_tabs_template',
        return_value='<div id="bucket-tabs">tabs</div>'
    ):
        result = view.build_bucket_tabs_oob_response(main_html='', request=request, active_bucket='bucket-1')

    assert 'id="bucket-tabs" hx-swap-oob="outerHTML"' in result
    assert 'id="current-active-bucket-input"' in result
    assert result.count('hx-swap-oob="outerHTML"') >= 2

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_ingest_bucket(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of a folder in the ingest bucket."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.get_folder_contents.return_value = {
        "items": [
            {"type": "folder", "name": "subfolder", "path": "folder1/subfolder/"},
            {"type": "file", "name": "test.txt", "path": "folder1/test.txt"}
        ],
        "has_more": False,
        "next_token": None,
    }
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/folder1/')
    load_folder_contents(request, 'ingest', 'folder1/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with('test-ingest-bucket', 'folder1/', force_fresh=False, continuation_token=None)
    
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
    mock_instance.get_all_accessible_buckets.return_value = ['ingest', 'production']
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.get_folder_contents.return_value = {
        "items": [
            {"type": "file", "name": "prod.txt", "path": "folder2/prod.txt"}
        ],
        "has_more": False,
        "next_token": None,
    }
    
    request = prepared_request('/storage/dashboard/folder-contents/production/folder2/')
    load_folder_contents(request, 'production', 'folder2/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with('test-production-bucket', 'folder2/', force_fresh=False, continuation_token=None)
    
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
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.get_folder_contents.return_value = {
        "items": [],
        "has_more": False,
        "next_token": None,
    }
    
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
