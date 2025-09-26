import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import boto3
from moto import mock_aws

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
    ocfl_service._compute_sha512_from_s3 = MagicMock(side_effect=[
        'digest-meta',
        'digest-acl',
        'digest-audio'
    ])

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

    put_calls = mock_bucket_service.s3_client.put_object.call_args_list
    inventory_keys = {call.kwargs['Key'] for call in put_calls}
    assert 'bundle_ocfl_12345678/inventory.json' in inventory_keys
    assert 'bundle_ocfl_12345678/v1/inventory.json' in inventory_keys
    assert 'bundle/inventory.json' in inventory_keys
    assert 'bundle/v1/inventory.json' in inventory_keys

    inventory_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle_ocfl_12345678/inventory.json')
    inventory_body = inventory_call.kwargs['Body']
    inventory_data = json.loads(inventory_body.decode('utf-8'))

    assert inventory_data['id'] == 'bundle'
    assert inventory_data['digestAlgorithm'] == 'sha512'
    assert inventory_data['head'] == 'v1'
    assert inventory_data['contentDirectory'] == 'content'
    assert set(inventory_data['manifest'].keys()) == {'digest-meta', 'digest-acl', 'digest-audio'}
    assert inventory_data['manifest']['digest-meta'] == ['v1/content/metadata/meta.xml']
    assert inventory_data['manifest']['digest-acl'] == ['v1/content/metadata/acl.json']
    assert inventory_data['manifest']['digest-audio'] == ['v1/content/Resources/files/audio.wav']

    state = inventory_data['versions']['v1']['state']
    assert set(state.keys()) == {'digest-meta', 'digest-acl', 'digest-audio'}
    assert state['digest-meta'] == ['metadata/meta.xml']
    assert state['digest-acl'] == ['metadata/acl.json']
    assert state['digest-audio'] == ['Resources/files/audio.wav']
    assert inventory_data['versions']['v1']['created'].endswith('Z')

    digest_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle_ocfl_12345678/inventory.json.sha512')
    digest_line = digest_call.kwargs['Body'].decode('utf-8').strip()
    digest_value, filename = digest_line.split()
    assert filename == 'inventory.json'
    assert digest_value == hashlib.sha512(inventory_body).hexdigest()

    v1_inventory_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle_ocfl_12345678/v1/inventory.json')
    assert v1_inventory_call.kwargs['Body'] == inventory_body

    v1_digest_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle_ocfl_12345678/v1/inventory.json.sha512')
    assert v1_digest_call.kwargs['Body'] == digest_call.kwargs['Body']

    final_inventory_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle/inventory.json')
    assert final_inventory_call.kwargs['Body'] == inventory_body

    final_digest_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle/inventory.json.sha512')
    assert final_digest_call.kwargs['Body'] == digest_call.kwargs['Body']

    final_v1_inventory_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle/v1/inventory.json')
    assert final_v1_inventory_call.kwargs['Body'] == inventory_body

    final_v1_digest_call = next(call for call in put_calls if call.kwargs['Key'] == 'bundle/v1/inventory.json.sha512')
    assert final_v1_digest_call.kwargs['Body'] == digest_call.kwargs['Body']

    ocfl_service._move_folder_contents.assert_called_once_with(
        'bucket', 'bundle_ocfl_12345678/', 'bundle/', delete_source=True
    )


@mock_aws
def test_server_side_conversion_creates_inventory_files():
    s3 = boto3.client('s3', region_name='us-east-1')
    bucket = 'test-bucket'
    s3.create_bucket(Bucket=bucket)

    # Seed legacy bundle structure
    s3.put_object(Bucket=bucket, Key='bundle/meta.xml', Body=b'<xml>meta</xml>')
    s3.put_object(Bucket=bucket, Key='bundle/acl.json', Body=b'{}')
    s3.put_object(Bucket=bucket, Key='bundle/files/audio.wav', Body=b'RIFFDATA')

    def list_bucket_contents(_bucket, prefix=""):
        if prefix and not prefix.endswith('/'):
            prefix = f"{prefix}/"
        response = s3.list_objects_v2(Bucket=_bucket, Prefix=prefix, Delimiter='/')
        contents = []
        for obj in response.get('Contents', []):
            if prefix and obj['Key'] == prefix:
                continue
            contents.append({
                'name': obj['Key'].split('/')[-1],
                'path': obj['Key'],
                'is_dir': False,
                'size': obj['Size']
            })
        for cp in response.get('CommonPrefixes', []):
            name = cp['Prefix'].rstrip('/').split('/')[-1]
            contents.append({'name': name, 'path': cp['Prefix'], 'is_dir': True})
        return contents

    bucket_service = SimpleNamespace(
        s3_client=s3,
        ingest_bucket=bucket,
        production_bucket=bucket,
        list_bucket_contents=list_bucket_contents
    )

    service = OCFLService(bucket_service)

    result = service._perform_server_side_conversion(
        bucket_name=bucket,
        folder_path='bundle',
        conversion_plan={'conversion_type': 'structured_to_ocfl', 'preserve_items': []}
    )

    assert result['success']

    response = s3.list_objects_v2(Bucket=bucket, Prefix='bundle/')
    keys = {obj['Key'] for obj in response.get('Contents', [])}

    expected_keys = {
        'bundle/0=ocfl_object_1.0',
        'bundle/v1/inventory.json',
        'bundle/v1/inventory.json.sha512',
        'bundle/inventory.json',
        'bundle/inventory.json.sha512',
        'bundle/v1/content/metadata/meta.xml',
        'bundle/v1/content/metadata/acl.json',
        'bundle/v1/content/Resources/files/audio.wav'
    }

    for expected in expected_keys:
        assert expected in keys

    # Ensure legacy files were removed
    assert 'bundle/meta.xml' not in keys
    assert 'bundle/acl.json' not in keys
    assert 'bundle/files/audio.wav' not in keys


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
