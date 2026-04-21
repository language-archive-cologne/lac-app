import json
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http.request import QueryDict

from lacos.storage.models import UploadSession
from lacos.storage.views.presigned_url_views import get_presigned_urls, mark_uploads_complete
from lacos.users.tests.factories import UserFactory


@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch('lacos.storage.views.presigned_url_views.resolve_storage_dashboard_bucket', return_value='resolved-bucket')
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
def test_get_presigned_urls_uses_resolved_bucket(
    mock_get_upload_service,
    _mock_resolve_bucket,
    _mock_ensure_collection_access,
    prepared_request,
):
    mock_instance = mock_get_upload_service.return_value
    mock_instance.ingest_bucket = 'ingest-bucket'
    mock_instance.generate_batch_presigned_posts.return_value = {
        "success": True,
        "presigned_posts": [{"success": True, "file_name": "test.jpg", "s3_key": "test-folder/test.jpg"}],
        "total_urls": 1,
        "total_failures": 0,
    }

    files_metadata = json.dumps([{"file_name": "test.jpg", "file_type": "image/jpeg"}])
    request = prepared_request(
        '/storage/presigned-urls/',
        method='post',
        data={'folder_name': 'test-folder', 'files_metadata': files_metadata},
    )
    request.POST = QueryDict('', mutable=True)
    request.POST.update({'folder_name': 'test-folder', 'files_metadata': files_metadata})

    response = get_presigned_urls(request)

    assert response.status_code == 200
    _, kwargs = mock_instance.generate_batch_presigned_posts.call_args
    assert kwargs['bucket_name'] == 'resolved-bucket'
    response_data = json.loads(response.content)
    assert response_data['success'] is True


@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch(
    'lacos.storage.views.presigned_url_views.resolve_storage_dashboard_bucket',
    side_effect=PermissionDenied("Bucket not allowed."),
)
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
def test_get_presigned_urls_rejects_disallowed_bucket(
    mock_get_upload_service,
    _mock_resolve_bucket,
    _mock_ensure_collection_access,
    prepared_request,
):
    files_metadata = json.dumps([{"file_name": "test.jpg", "file_type": "image/jpeg"}])
    request = prepared_request(
        '/storage/presigned-urls/',
        method='post',
        data={'folder_name': 'test-folder', 'files_metadata': files_metadata, 'bucket_name': 'private-bucket'},
    )
    request.POST = QueryDict('', mutable=True)
    request.POST.update({
        'folder_name': 'test-folder',
        'files_metadata': files_metadata,
        'bucket_name': 'private-bucket',
    })

    response = get_presigned_urls(request)

    assert response.status_code == 403
    response_data = json.loads(response.content)
    assert response_data['success'] is False
    assert response_data['error'] == 'Bucket not allowed.'
    mock_get_upload_service.return_value.generate_batch_presigned_posts.assert_not_called()


@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch('lacos.storage.views.presigned_url_views.resolve_storage_dashboard_bucket', return_value='resolved-bucket')
@patch('lacos.storage.views.presigned_url_views.UploadVerificationService')
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
@pytest.mark.django_db
def test_mark_uploads_complete_uses_resolved_bucket(
    mock_get_upload_service,
    MockUploadVerificationService,
    _mock_resolve_bucket,
    _mock_ensure_collection_access,
    prepared_request,
):
    upload_service = mock_get_upload_service.return_value
    upload_service.ingest_bucket = 'ingest-bucket'
    verification_service = MockUploadVerificationService.return_value
    verification_service.verify_keys.return_value = {
        "success": True,
        "results": [],
        "total_verified": 1,
        "total_failed": 0,
        "total_size": 1024,
        "total_size_formatted": "1.00 KB",
    }

    json_data = {"s3_keys": ["collection-a/test.jpg"], "bucket_name": "ingest"}
    request = prepared_request(
        '/storage/mark-uploads-complete/',
        method='post',
        data=json_data,
        content_type='application/json',
    )
    request._body = json.dumps(json_data).encode('utf-8')

    response = mark_uploads_complete(request)

    assert response.status_code == 200
    verification_service.verify_keys.assert_called_once_with(
        ["collection-a/test.jpg"],
        upload_session=None,
        bucket_name='resolved-bucket',
    )


@patch('lacos.storage.views.presigned_url_views._ensure_collection_access', return_value=None)
@patch('lacos.storage.views.presigned_url_views.get_upload_service')
@pytest.mark.django_db
def test_mark_uploads_complete_rejects_unowned_session(
    mock_get_upload_service,
    _mock_ensure_collection_access,
    prepared_request,
):
    upload_service = mock_get_upload_service.return_value
    upload_service.ingest_bucket = 'ingest-bucket'

    owner = UserFactory()
    request_user = UserFactory()
    request_user.groups.add(Group.objects.get_or_create(name="collection_manager")[0])
    upload_session = UploadSession.objects.create(
        user=owner,
        folder_name='collection-a',
        bucket_name='ingest-bucket',
    )

    json_data = {
        "s3_keys": ["collection-a/test.jpg"],
        "upload_session_id": str(upload_session.id),
    }
    request = prepared_request(
        '/storage/mark-uploads-complete/',
        method='post',
        data=json_data,
        content_type='application/json',
    )
    request.user = request_user
    request._body = json.dumps(json_data).encode('utf-8')

    response = mark_uploads_complete(request)

    assert response.status_code == 403
    response_data = json.loads(response.content)
    assert response_data['success'] is False
    assert response_data['error'] == 'Upload session not owned by current user.'
