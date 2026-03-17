import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import force_authenticate

from lacos.rest.views.upload_views import (
    get_upload_url,
    get_batch_upload_urls,
    get_accelerated_upload_url,
    mark_upload_complete,
    get_folder_upload_urls
)


@pytest.fixture
def request_factory():
    """Fixture for a request factory."""
    return RequestFactory()


@pytest.fixture
def authenticated_user():
    """Fixture for an authenticated user."""
    user = MagicMock()
    user.username = "testuser"
    user.is_authenticated = True
    return user


class TestUploadViews:
    """Test cases for the upload-related views."""

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_upload_url_success(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test successful generation of a presigned URL."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.generate_presigned_post.return_value = {
            'success': True,
            'file_name': 'test.jpg',
            's3_key': 'folder/test.jpg',
            'url': 'https://test-bucket.s3.amazonaws.com',
            'fields': {'key': 'folder/test.jpg'},
            'expires_in': 3600
        }

        # Make the request
        request = request_factory.post(
            '/api/get-upload-url/', 
            data={
                'file_name': 'test.jpg',
                'file_type': 'image/jpeg',
                'folder_name': 'folder'
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['file_name'] == 'test.jpg'
        assert response.data['s3_key'] == 'folder/test.jpg'
        
        # Verify the service was called with correct parameters
        mock_instance.generate_presigned_post.assert_called_once_with(
            file_name='test.jpg',
            file_type='image/jpeg',
            path_prefix='folder'
        )

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_upload_url_missing_params(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test generation of a presigned URL with missing parameters."""
        # Make the request with missing file_type
        request = request_factory.post(
            '/api/get-upload-url/',
            data={'file_name': 'test.jpg'},
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.generate_presigned_post.assert_not_called()

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_upload_url_service_error(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test handling of service errors when generating a presigned URL."""
        # Configure the mock to return an error
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.generate_presigned_post.return_value = {
            'success': False,
            'error': 'Service unavailable',
            'file_name': 'test.jpg'
        }

        # Make the request
        request = request_factory.post(
            '/api/get-upload-url/',
            data={
                'file_name': 'test.jpg',
                'file_type': 'image/jpeg',
                'folder_name': 'folder'
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data['success'] is False
        assert response.data['error'] == 'Service unavailable'

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_batch_upload_urls_success(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test successful generation of batch presigned URLs."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.generate_batch_presigned_posts.return_value = {
            'success': True,
            'presigned_posts': [
                {
                    'success': True,
                    'file_name': 'test1.jpg',
                    's3_key': 'folder/test1.jpg',
                    'presigned_post': {
                        'url': 'https://test-bucket.s3.amazonaws.com',
                        'fields': {'key': 'folder/test1.jpg'}
                    }
                },
                {
                    'success': True,
                    'file_name': 'test2.jpg',
                    's3_key': 'folder/test2.jpg',
                    'presigned_post': {
                        'url': 'https://test-bucket.s3.amazonaws.com',
                        'fields': {'key': 'folder/test2.jpg'}
                    }
                }
            ],
            'failures': [],
            'total_urls': 2,
            'total_failures': 0
        }

        # Make the request
        data = {
            'files': [
                {'file_name': 'test1.jpg', 'file_type': 'image/jpeg'},
                {'file_name': 'test2.jpg', 'file_type': 'image/jpeg'}
            ],
            'folder_name': 'folder',
            'expiration': 7200
        }
        request = request_factory.post(
            '/api/get-batch-upload-urls/',
            data=data,
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_batch_upload_urls(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['presigned_posts']) == 2
        assert response.data['total_urls'] == 2
        assert response.data['total_failures'] == 0
        
        # Verify the service was called with correct parameters
        mock_instance.generate_batch_presigned_posts.assert_called_once_with(
            files_metadata=data['files'],
            path_prefix='folder',
            expiration=7200
        )

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_folder_upload_urls_success(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test successful generation of folder upload URLs."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.generate_batch_presigned_posts.return_value = {
            'success': True,
            'presigned_posts': [
                {
                    'success': True,
                    'file_name': 'test1.jpg',
                    'path': 'images',
                    's3_key': 'my_folder/images/test1.jpg',
                    'presigned_post': {
                        'url': 'https://test-bucket.s3.amazonaws.com',
                        'fields': {'key': 'my_folder/images/test1.jpg'}
                    }
                },
                {
                    'success': True,
                    'file_name': 'test2.jpg',
                    'path': 'images/subfolder',
                    's3_key': 'my_folder/images/subfolder/test2.jpg',
                    'presigned_post': {
                        'url': 'https://test-bucket.s3.amazonaws.com',
                        'fields': {'key': 'my_folder/images/subfolder/test2.jpg'}
                    }
                }
            ],
            'failures': [],
            'total_urls': 2,
            'total_failures': 0
        }

        # Make the request
        data = {
            'folder_name': 'my_folder',
            'folder_structure': [
                {
                    'filename': 'test1.jpg',
                    'content_type': 'image/jpeg',
                    'path': 'images',
                    'size': 12345
                },
                {
                    'filename': 'test2.jpg',
                    'content_type': 'image/jpeg',
                    'path': 'images/subfolder',
                    'size': 67890
                }
            ]
        }
        request = request_factory.post(
            '/api/get-folder-upload-urls/',
            data=data,
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_folder_upload_urls(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['urls']) == 2
        assert response.data['total_urls'] == 2
        assert response.data['folder_name'] == 'my_folder'
        
        # Check that the original paths are preserved
        assert response.data['urls'][0]['original_path'] == 'images/test1.jpg'
        assert response.data['urls'][1]['original_path'] == 'images/subfolder/test2.jpg'
        
        # Verify the service was called with correct parameters
        expected_files_metadata = [
            {
                'file_name': 'test1.jpg',
                'file_type': 'image/jpeg',
                'path': 'images',
                'size': 12345
            },
            {
                'file_name': 'test2.jpg',
                'file_type': 'image/jpeg',
                'path': 'images/subfolder',
                'size': 67890
            }
        ]
        
        mock_instance.generate_batch_presigned_posts.assert_called_once()
        call_args = mock_instance.generate_batch_presigned_posts.call_args[1]
        assert call_args['path_prefix'] == 'my_folder'
        assert call_args['expiration'] == 3600
        assert len(call_args['files_metadata']) == 2
        # We can't directly compare dicts because order might be different
        for expected, actual in zip(expected_files_metadata, call_args['files_metadata']):
            assert expected['file_name'] == actual['file_name']
            assert expected['file_type'] == actual['file_type']
            assert expected['path'] == actual['path']
            assert expected['size'] == actual['size']

    @patch('lacos.rest.views.upload_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.upload_views.UploadService')
    def test_get_folder_upload_urls_missing_folder_name(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test folder upload URL generation with missing folder name."""
        # Make the request without folder_name
        data = {
            'folder_structure': [
                {'filename': 'test1.jpg', 'content_type': 'image/jpeg', 'path': 'images', 'size': 12345}
            ]
        }
        request = request_factory.post(
            '/api/get-folder-upload-urls/',
            data=data,
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = get_folder_upload_urls(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing folder_name parameter' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.generate_batch_presigned_posts.assert_not_called()

    def test_get_upload_url_requires_authentication(self, request_factory):
        request = request_factory.post(
            '/api/get-upload-url/',
            data={
                'file_name': 'test.jpg',
                'file_type': 'image/jpeg',
                'folder_name': 'folder',
            },
            content_type='application/json'
        )
        response = get_upload_url(request)

        assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
