import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest

from lacos.storage.services.ocfl_service import OCFLService


@pytest.fixture
def mock_bucket_service():
    service = Mock()
    service.s3_client = MagicMock()
    return service


@pytest.fixture
def ocfl_service(mock_bucket_service):
    return OCFLService(mock_bucket_service)


@patch('lacos.storage.services.ocfl_service.uuid.uuid4')
def test_server_side_conversion_success(mock_uuid, ocfl_service, mock_bucket_service):
    mock_uuid.return_value = uuid.UUID('12345678123456781234567812345678')

    ocfl_service._list_s3_objects = MagicMock(return_value=[
        'bundle/meta.xml',
        'bundle/acl.json',
        'bundle/files/audio.wav'
    ])
    ocfl_service._delete_folder_contents = MagicMock()
    ocfl_service._move_folder_contents = MagicMock()

    result = ocfl_service._perform_server_side_conversion(
        bucket_name='bucket',
        folder_path='bundle',
        conversion_plan={'conversion_type': 'structured_to_ocfl', 'preserve_items': []}
    )

    assert result['success']
    assert result['files_processed'] == 3
    assert result['metadata_files'] == ['meta.xml']

    copy_calls = mock_bucket_service.s3_client.copy_object.call_args_list
    keys = {call.kwargs['Key'] for call in copy_calls}
    assert 'bundle_ocfl_12345678/v1/content/metadata/meta.xml' in keys
    assert 'bundle_ocfl_12345678/v1/content/metadata/acl.json' in keys
    assert 'bundle_ocfl_12345678/v1/content/Resources/files/audio.wav' in keys

    ocfl_service._move_folder_contents.assert_called_once_with(
        'bucket', 'bundle_ocfl_12345678/', 'bundle/', delete_source=True
    )


@patch('lacos.storage.services.ocfl_service.uuid.uuid4')
def test_server_side_conversion_failure_cleans_temp(mock_uuid, ocfl_service):
    mock_uuid.return_value = uuid.UUID('12345678123456781234567812345678')

    ocfl_service._list_s3_objects = MagicMock(side_effect=RuntimeError('boom'))
    ocfl_service._delete_folder_contents = MagicMock()

    result = ocfl_service._perform_server_side_conversion(
        bucket_name='bucket',
        folder_path='bundle',
        conversion_plan={'conversion_type': 'structured_to_ocfl'}
    )

    assert not result['success']
    assert result['server_side']
    ocfl_service._delete_folder_contents.assert_called_with('bucket', 'bundle_ocfl_12345678/')


@patch.object(OCFLService, '_perform_server_side_conversion')
def test_atomic_conversion_prefers_server_side(mock_server, ocfl_service, mock_bucket_service):
    mock_server.return_value = {'success': True, 'server_side': True}

    result = ocfl_service._perform_atomic_conversion(
        bucket_name='bucket',
        folder_path='bundle',
        conversion_plan={'conversion_type': 'structured_to_ocfl'}
    )

    assert result['success']
    mock_server.assert_called_once()
    mock_bucket_service._download_directory.assert_not_called()
