import pytest
from unittest.mock import MagicMock
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _login_user(client, django_user_model):
    user = django_user_model.objects.create_user(
        username='tester',
        email='tester@example.com',
        password='password123',
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    return user


def test_preview_metadata_ingest_shows_collection_pipeline(client, django_user_model, monkeypatch):
    _login_user(client, django_user_model)

    mock_service = MagicMock()
    mock_service.find_collection_and_bundle_xmls_s3.return_value = {
        'potential_collection_xmls': ['col1/col1/v1/content/col1.xml'],
        'potential_bundle_xmls': [
            'col1/bun1/v1/content/bun1.xml',
            'col1/bun2/v1/content/bun2.xml',
        ],
    }
    monkeypatch.setattr(
        'lacos.storage.views.metadata_ingest_views.FileDiscoveryService',
        lambda: mock_service,
    )

    response = client.get(
        reverse('storage:preview_metadata_ingest'),
        {
            'bucket': 'test-bucket',
            's3_key': 'col1/col1/v1/content/col1.xml',
            'object_type': 'file',
            'metadata_type': 'collection',
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'Found 1 collection' in content
    assert 'name="use_pipeline" value="true"' in content
    assert 'col1/bun1/v1/content/bun1.xml' in content


def test_ingest_metadata_uses_pipeline_when_requested(client, django_user_model, monkeypatch):
    _login_user(client, django_user_model)

    process_mock = MagicMock()
    import_collection_mock = MagicMock()
    import_bundle_mock = MagicMock()
    monkeypatch.setattr('lacos.storage.views.metadata_ingest_views.process_s3_prefix', process_mock)
    monkeypatch.setattr('lacos.storage.views.metadata_ingest_views.import_s3_collection', import_collection_mock)
    monkeypatch.setattr('lacos.storage.views.metadata_ingest_views.import_s3_bundle', import_bundle_mock)

    response = client.post(
        reverse('storage:ingest_metadata'),
        {
            'metadata_type': 'collection',
            'bucket': 'test-bucket',
            's3_key': 'col1/col1/v1/content/col1.xml',
            'use_pipeline': 'true',
            'pipeline_prefix': 'col1/',
            'preview_collection_count': '1',
            'preview_bundle_count': '2',
        },
        HTTP_HX_REQUEST='true',
    )

    assert response.status_code == 200
    process_mock.assert_called_once_with(bucket='test-bucket', prefix='col1/')
    import_collection_mock.assert_not_called()
    import_bundle_mock.assert_not_called()
    assert 'Collection ingest pipeline queued' in response.content.decode()
