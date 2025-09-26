from unittest.mock import patch

from lacos.storage.tasks import convert_folder_to_ocfl_task


@patch('lacos.storage.tasks.OCFLService')
@patch('lacos.storage.tasks.BucketService')
def test_convert_task_returns_success(mock_bucket_service, mock_ocfl_service):
    ocfl_instance = mock_ocfl_service.return_value
    ocfl_instance.analyze_folder_structure.return_value = {
        'success': True,
        'folder_path': 'bucket/prefix/',
        'structure_analysis': {
            'has_metadata_files': False,
            'has_ocfl_marker': False,
            'total_files': 1,
            'partial_ocfl': False,
        }
    }
    ocfl_instance.convert_bundle_to_ocfl.return_value = {
        'success': True,
        'message': 'ok',
        'conversion_type': 'flat_to_ocfl',
        'server_side': True
    }

    result = convert_folder_to_ocfl_task.call_local(
        bucket_name='bucket',
        folder_path='prefix/',
        create_backup=False,
        force=True
    )

    assert result['success']
    assert result['bucket_name'] == 'bucket'
    assert result['folder_path'] == 'prefix/'
    ocfl_instance.convert_bundle_to_ocfl.assert_called_once_with('bucket', 'prefix/')


@patch('lacos.storage.tasks.OCFLService')
@patch('lacos.storage.tasks.BucketService')
def test_convert_task_propagates_error(mock_bucket_service, mock_ocfl_service):
    ocfl_instance = mock_ocfl_service.return_value
    ocfl_instance.analyze_folder_structure.return_value = {
        'success': True,
        'folder_path': 'bucket/prefix/',
        'structure_analysis': {
            'has_metadata_files': False,
            'has_ocfl_marker': False,
            'total_files': 1,
            'partial_ocfl': False,
        }
    }
    ocfl_instance.convert_bundle_to_ocfl.return_value = {
        'success': False,
        'error': 'fail'
    }

    result = convert_folder_to_ocfl_task.call_local(
        bucket_name='bucket',
        folder_path='prefix/',
        create_backup=False,
        force=True
    )

    assert not result['success']
    assert result['error'] == 'fail'
