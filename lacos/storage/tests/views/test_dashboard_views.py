import pytest
from unittest.mock import patch, MagicMock

from django.urls import reverse

from lacos.storage.views.dashboard_views import (
    BucketContentHTMXView,
    archivist_dashboard,
    load_folder_contents,
    RenameBucketHTMXView,
    RenameBucketModalHTMXView,
    RenameObjectModalHTMXView,
)
from lacos.common.mixins.htmx_template_helpers import HtmxTemplateHelperMixin, ROOT_FOLDER_SENTINEL
from lacos.storage.services.collection_service import BucketListingPage

# Note: fixtures are now imported from conftest.py automatically

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_success(mock_render, mock_bucket_service, prepared_request):
    """Dashboard renders with bucket metadata and defers structure loading."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = ['test-production-bucket']

    request = prepared_request('/storage/dashboard/', method='get', data={'message': 'Test message'})

    archivist_dashboard(request)

    mock_instance.get_root_level_items.assert_not_called()
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]

    assert template_name == "dashboard/archivist_dashboard.html"
    assert context['workspace_buckets'] == ['test-ingest-bucket', 'test-production-bucket']
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['message'] == 'Test message'
    assert context['auto_load_url'] == reverse('storage:bucket_content_htmx', kwargs={'bucket_name': 'test-ingest-bucket'})
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_empty_buckets(mock_render, mock_bucket_service, prepared_request):
    """Test dashboard loading with empty buckets."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = []

    request = prepared_request('/storage/dashboard/')
    archivist_dashboard(request)
    
    mock_instance.get_root_level_items.assert_not_called()
    context = mock_render.call_args[0][2]
    assert context['workspace_buckets'] == ['test-ingest-bucket', 'test-production-bucket']
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['message'] is None
    assert context['auto_load_url'] == reverse('storage:bucket_content_htmx', kwargs={'bucket_name': 'test-ingest-bucket'})
    assert request.session['storage_active_bucket'] == 'test-ingest-bucket'

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_archivist_dashboard_force_fresh_propagates(mock_render, mock_bucket_service, prepared_request):
    """Force fresh param should flow through auto-load URL."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.ocfl_buckets = []
    
    request = prepared_request('/storage/dashboard/?force_fresh=true')
    archivist_dashboard(request)
    
    context = mock_render.call_args[0][2]
    assert context['active_bucket'] == 'test-ingest-bucket'
    assert context['auto_load_url'].endswith('?force_fresh=true')
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


@patch('lacos.storage.services.bucket_service.BucketService')
@patch('lacos.common.mixins.htmx_template_helpers.render_to_string', return_value='rendered')
@patch('lacos.common.mixins.htmx_template_helpers.get_token', return_value='csrf-token')
def test_render_bucket_content_template_defers_root_listing(mock_get_token, mock_render_to_string, MockBucketService, prepared_request):
    """When prefetch_root=False the mixin should skip fetching contents and enable autoload."""
    view = _DummyHelperView()
    mock_service = MockBucketService.return_value
    mock_service.get_all_accessible_buckets.return_value = ['demo-bucket']
    mock_service.ocfl_buckets = []
    mock_service.dashboard_pagination_enabled = True
    mock_service.dashboard_page_size = 200

    request = prepared_request('/storage/demo/', method='get')
    html = view.render_bucket_content_template(request, 'demo-bucket', prefetch_root=False)

    assert html == 'rendered'
    mock_service.get_folder_contents.assert_not_called()
    template_name, context = mock_render_to_string.call_args[0]
    assert mock_render_to_string.call_args.kwargs.get('request') is request
    assert template_name == 'dashboard/bucket_content_partial.html'
    assert context['listing'] is None
    assert context['root_autoload'] is True
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL
    assert ROOT_FOLDER_SENTINEL in context['root_load_url']


@patch('lacos.storage.services.bucket_service.BucketService')
@patch('lacos.common.mixins.htmx_template_helpers.render_to_string', return_value='rendered')
@patch('lacos.common.mixins.htmx_template_helpers.get_token', return_value='csrf-token')
def test_render_bucket_content_template_prefetches_root(mock_get_token, mock_render_to_string, MockBucketService, prepared_request):
    """Default behaviour should eagerly fetch root contents."""
    view = _DummyHelperView()
    mock_service = MockBucketService.return_value
    mock_service.get_all_accessible_buckets.return_value = ['demo-bucket']
    mock_service.ocfl_buckets = []
    mock_service.dashboard_pagination_enabled = True
    mock_service.dashboard_page_size = 50
    listing = BucketListingPage(items=[], has_more=False, next_token=None, bucket='demo-bucket', prefix='')
    mock_service.get_folder_contents.return_value = listing

    request = prepared_request('/storage/demo/', method='get')
    html = view.render_bucket_content_template(request, 'demo-bucket')

    assert html == 'rendered'
    mock_service.get_folder_contents.assert_called_once_with(
        'demo-bucket',
        '',
        max_keys=50,
        continuation_token=None,
        force_fresh=False,
    )
    template_name, context = mock_render_to_string.call_args[0]
    assert mock_render_to_string.call_args.kwargs.get('request') is request
    assert context['listing'] is listing
    assert context['root_autoload'] is False
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_ingest_bucket(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of a folder in the ingest bucket."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.dashboard_page_size = 25
    mock_instance.dashboard_pagination_enabled = True
    listing = BucketListingPage(
        items=[
            {"type": "folder", "name": "subfolder", "path": "folder1/subfolder/"},
            {"type": "file", "name": "test.txt", "path": "folder1/test.txt"},
        ],
        has_more=False,
        next_token=None,
        bucket='test-ingest-bucket',
        prefix='folder1/',
    )
    mock_instance.get_folder_contents.return_value = listing
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/folder1/')
    load_folder_contents(request, 'ingest', 'folder1/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with(
        'test-ingest-bucket',
        'folder1/',
        max_keys=25,
        continuation_token=None,
        force_fresh=False,
    )
    
    # Verify template rendering
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/folder_contents_partial.html"
    assert context['bucket_type'] == 'ingest'
    assert context['folder_path'] == 'folder1/'
    assert context['folder_path_param'] == 'folder1/'
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL
    assert isinstance(context['listing'], BucketListingPage)
    assert len(context['listing']) == 2
    assert context['listing'].has_more is False
    assert context['max_keys'] == 25
    assert context['is_root'] is False

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_production_bucket(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of a folder in the production bucket."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.dashboard_page_size = 10
    mock_instance.dashboard_pagination_enabled = True
    listing = BucketListingPage(
        items=[{"type": "file", "name": "prod.txt", "path": "folder2/prod.txt"}],
        has_more=True,
        next_token="next-token",
        bucket='test-production-bucket',
        prefix='folder2/',
    )
    mock_instance.get_folder_contents.return_value = listing
    
    request = prepared_request('/storage/dashboard/folder-contents/production/folder2/')
    load_folder_contents(request, 'production', 'folder2/')
    
    # Verify service was called with correct parameters
    mock_instance.get_folder_contents.assert_called_once_with(
        'test-production-bucket',
        'folder2/',
        max_keys=10,
        continuation_token=None,
        force_fresh=False,
    )
    
    # Verify template rendering
    mock_render.assert_called_once()
    template_name = mock_render.call_args[0][1]
    context = mock_render.call_args[0][2]
    
    assert template_name == "dashboard/folder_contents_partial.html"
    assert context['bucket_type'] == 'production'
    assert context['folder_path'] == 'folder2/'
    assert context['folder_path_param'] == 'folder2/'
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL
    assert context['listing'].has_more is True
    assert context['listing'].next_token == "next-token"
    assert context['is_root'] is False

@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_empty_folder(mock_render, mock_bucket_service, prepared_request):
    """Test loading contents of an empty folder."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.dashboard_page_size = 15
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[],
        has_more=False,
        next_token=None,
        bucket='test-ingest-bucket',
        prefix='empty_folder/',
    )
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/empty_folder/')
    load_folder_contents(request, 'ingest', 'empty_folder/')
    
    # Verify template rendering with empty contents
    mock_render.assert_called_once()
    context = mock_render.call_args[0][2]
    assert context['folder_path'] == 'empty_folder/'
    assert context['folder_path_param'] == 'empty_folder/'
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL
    assert context['is_root'] is False
    assert len(context['listing']) == 0
    assert context['listing'].has_more is False


@patch('lacos.storage.views.dashboard_views.BucketService')
@patch('lacos.storage.views.dashboard_views.render')
def test_load_folder_contents_respects_pagination_flag(mock_render, mock_bucket_service, prepared_request):
    """Pagination flag should disable max_keys usage."""
    mock_instance = mock_bucket_service.return_value
    mock_instance.ingest_bucket = 'test-ingest-bucket'
    mock_instance.production_bucket = 'test-production-bucket'
    mock_instance.dashboard_page_size = 99
    mock_instance.dashboard_pagination_enabled = False
    mock_instance.get_all_accessible_buckets.return_value = ['test-ingest-bucket', 'test-production-bucket']
    mock_instance.get_folder_contents.return_value = BucketListingPage(
        items=[{"type": "file", "name": "a.txt", "path": "root/a.txt"}],
        has_more=False,
        next_token=None,
        bucket='test-ingest-bucket',
        prefix='',
    )

    request = prepared_request('/storage/dashboard/folder-contents/test-ingest-bucket/__root__/')
    load_folder_contents(request, 'test-ingest-bucket', ROOT_FOLDER_SENTINEL)

    mock_instance.get_folder_contents.assert_called_once()
    args, kwargs = mock_instance.get_folder_contents.call_args
    assert args[:2] == ('test-ingest-bucket', '')
    assert kwargs.get('max_keys') is None
    assert kwargs.get('continuation_token') is None
    assert kwargs.get('force_fresh') is False
    mock_render.assert_called_once()
    context = mock_render.call_args[0][2]
    assert context['folder_path'] == ''
    assert context['folder_path_param'] == ROOT_FOLDER_SENTINEL
    assert context['is_root'] is True
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL


@patch.object(BucketContentHTMXView, 'render_bucket_content_template', return_value='content-html')
@patch.object(BucketContentHTMXView, 'build_bucket_tabs_oob_response', return_value='')
def test_bucket_content_htmx_defers_root_loading(mock_build_tabs, mock_render_content, prepared_request):
    request = prepared_request('/storage/htmx/bucket-content/demo/', method='get', htmx=True)
    response = BucketContentHTMXView.as_view()(request, bucket_name='demo')

    assert response.status_code == 200
    mock_render_content.assert_called_once_with(
        request,
        'demo',
        continuation_token=None,
        max_keys=None,
        force_fresh=False,
        prefetch_root=False,
    )
    mock_build_tabs.assert_called_once()


@patch.object(BucketContentHTMXView, 'render_bucket_content_template', return_value='content-html')
@patch.object(BucketContentHTMXView, 'build_bucket_tabs_oob_response', return_value='')
def test_bucket_content_htmx_prefetches_when_paginated(mock_build_tabs, mock_render_content, prepared_request):
    request = prepared_request(
        '/storage/htmx/bucket-content/demo/?max_keys=100',
        method='get',
        htmx=True,
        data={'max_keys': '100'},
    )
    response = BucketContentHTMXView.as_view()(request, bucket_name='demo')

    assert response.status_code == 200
    mock_render_content.assert_called_once_with(
        request,
        'demo',
        continuation_token=None,
        max_keys=100,
        force_fresh=False,
        prefetch_root=True,
    )
    mock_build_tabs.assert_called_once()


@patch.object(BucketContentHTMXView, 'render_bucket_content_template', return_value='content-html')
@patch.object(BucketContentHTMXView, 'build_bucket_tabs_oob_response', return_value='')
def test_bucket_content_htmx_prefetch_override(mock_build_tabs, mock_render_content, prepared_request):
    request = prepared_request(
        '/storage/htmx/bucket-content/demo/?prefetch_root=true',
        method='get',
        htmx=True,
        data={'prefetch_root': 'true'},
    )
    response = BucketContentHTMXView.as_view()(request, bucket_name='demo')

    assert response.status_code == 200
    mock_render_content.assert_called_once_with(
        request,
        'demo',
        continuation_token=None,
        max_keys=None,
        force_fresh=False,
        prefetch_root=True,
    )
    mock_build_tabs.assert_called_once()


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
    mock_instance.dashboard_page_size = 30
    mock_instance.dashboard_pagination_enabled = True
    mock_instance.get_folder_contents.side_effect = Exception("Service error")
    
    request = prepared_request('/storage/dashboard/folder-contents/ingest/error_folder/')
    load_folder_contents(request, 'ingest', 'error_folder/')
    
    # Verify empty list is returned on error
    mock_render.assert_called_once()
    context = mock_render.call_args[0][2]
    assert context['folder_path'] == 'error_folder/'
    assert context['folder_path_param'] == 'error_folder/'
    assert context['root_folder_sentinel'] == ROOT_FOLDER_SENTINEL
    assert context['is_root'] is False
    assert len(context['listing']) == 0
    assert context['listing'].has_more is False
