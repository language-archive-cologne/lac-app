import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import force_authenticate

from lacos.rest import views


@pytest.fixture
def request_factory():
    """Fixture for a request factory."""
    return RequestFactory()


class TestUploadViews:
    """Test cases for the upload-related views."""

    @patch('lacos.rest.views.UploadService')
    def test_get_upload_url_success(self, mock_upload_service, request_factory):
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
            '/api/s3/upload/url/', 
            data={
                'file_name': 'test.jpg',
                'file_type': 'image/jpeg',
                'folder_name': 'folder'
            },
            content_type='application/json'
        )
        response = views.get_upload_url(request)

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

    @patch('lacos.rest.views.UploadService')
    def test_get_upload_url_missing_params(self, mock_upload_service, request_factory):
        """Test generation of a presigned URL with missing parameters."""
        # Make the request with missing file_type
        request = request_factory.post(
            '/api/s3/upload/url/',
            data={'file_name': 'test.jpg'},
            content_type='application/json'
        )
        response = views.get_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.generate_presigned_post.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_get_upload_url_service_error(self, mock_upload_service, request_factory):
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
            '/api/s3/upload/url/',
            data={
                'file_name': 'test.jpg',
                'file_type': 'image/jpeg'
            },
            content_type='application/json'
        )
        response = views.get_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data['success'] is False
        assert response.data['error'] == 'Service unavailable'

    @patch('lacos.rest.views.UploadService')
    def test_get_batch_upload_urls_success(self, mock_upload_service, request_factory):
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
                    'url': 'https://test-bucket.s3.amazonaws.com',
                    'fields': {'key': 'folder/test1.jpg'},
                    'expires_in': 3600
                },
                {
                    'success': True,
                    'file_name': 'test2.jpg',
                    's3_key': 'folder/test2.jpg',
                    'url': 'https://test-bucket.s3.amazonaws.com',
                    'fields': {'key': 'folder/test2.jpg'},
                    'expires_in': 3600
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
            '/api/s3/upload/batch-urls/',
            data=data,
            content_type='application/json'
        )
        response = views.get_batch_upload_urls(request)

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

    @patch('lacos.rest.views.UploadService')
    def test_get_batch_upload_urls_missing_files(self, mock_upload_service, request_factory):
        """Test batch presigned URL generation with missing files parameter."""
        # Make the request without files
        request = request_factory.post(
            '/api/s3/upload/batch-urls/',
            data={'folder_name': 'folder'},
            content_type='application/json'
        )
        response = views.get_batch_upload_urls(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing or invalid' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.generate_batch_presigned_posts.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_get_accelerated_upload_url_success(self, mock_upload_service, request_factory):
        """Test successful generation of an accelerated upload URL."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.get_upload_url_with_acceleration.return_value = {
            'success': True,
            'file_name': 'test.mp4',
            's3_key': 'videos/test.mp4',
            'url': 'https://test-bucket.s3-accelerate.amazonaws.com',
            'fields': {'key': 'videos/test.mp4'},
            'expires_in': 3600,
            'acceleration_enabled': True
        }

        # Make the request
        request = request_factory.post(
            '/api/s3/upload/accelerated-url/',
            data={
                'file_name': 'test.mp4',
                'file_type': 'video/mp4',
                'folder_name': 'videos'
            },
            content_type='application/json'
        )
        response = views.get_accelerated_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['file_name'] == 'test.mp4'
        assert response.data['s3_key'] == 'videos/test.mp4'
        assert response.data['acceleration_enabled'] is True
        
        # Verify the service was called with correct parameters
        mock_instance.get_upload_url_with_acceleration.assert_called_once_with(
            file_name='test.mp4',
            file_type='video/mp4',
            path_prefix='videos'
        )

    @patch('lacos.rest.views.UploadService')
    def test_get_accelerated_upload_url_missing_params(self, mock_upload_service, request_factory):
        """Test accelerated upload URL generation with missing parameters."""
        # Make the request with missing file_type
        request = request_factory.post(
            '/api/s3/upload/accelerated-url/',
            data={'file_name': 'test.mp4'},
            content_type='application/json'
        )
        response = views.get_accelerated_upload_url(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.get_upload_url_with_acceleration.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_mark_upload_complete_success(self, mock_upload_service, request_factory):
        """Test successful marking of an upload as complete."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.mark_upload_complete.return_value = {
            'success': True,
            's3_key': 'folder/test.jpg',
            'exists': True,
            'file_size': 1024,
            'file_size_formatted': '1.00 KB',
            'content_type': 'image/jpeg',
            'last_modified': '2023-07-25T12:34:56Z'
        }

        # Make the request
        request = request_factory.post(
            '/api/s3/upload/complete/',
            data={'s3_key': 'folder/test.jpg'},
            content_type='application/json'
        )
        response = views.mark_upload_complete(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['s3_key'] == 'folder/test.jpg'
        assert response.data['exists'] is True
        assert response.data['file_size'] == 1024
        
        # Verify the service was called with correct parameters
        mock_instance.mark_upload_complete.assert_called_once_with('folder/test.jpg')

    @patch('lacos.rest.views.UploadService')
    def test_mark_upload_complete_missing_key(self, mock_upload_service, request_factory):
        """Test marking upload complete with missing s3_key parameter."""
        # Make the request without s3_key
        request = request_factory.post(
            '/api/s3/upload/complete/',
            data={},
            content_type='application/json'
        )
        response = views.mark_upload_complete(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameter' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.mark_upload_complete.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_mark_upload_complete_file_not_found(self, mock_upload_service, request_factory):
        """Test handling when the uploaded file is not found."""
        # Configure the mock to return a file not found error
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.mark_upload_complete.return_value = {
            'success': False,
            'error': 'File not found',
            's3_key': 'folder/missing.jpg',
            'exists': False
        }

        # Make the request
        request = request_factory.post(
            '/api/s3/upload/complete/',
            data={'s3_key': 'folder/missing.jpg'},
            content_type='application/json'
        )
        response = views.mark_upload_complete(request)

        # Assert response
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data['success'] is False
        assert response.data['s3_key'] == 'folder/missing.jpg'
        assert response.data['exists'] is False

    @patch('lacos.rest.views.UploadService')
    def test_process_uploaded_files_success(self, mock_upload_service, request_factory):
        """Test successful processing of uploaded files."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.check_file_exists.return_value = True
        mock_instance.get_object_content.return_value = "<xml>test content</xml>"
        
        # Create a user for authentication
        user = MagicMock()
        user.is_authenticated = True
        
        # Make the request
        uploaded_files = [
            {'s3_key': 'folder/test.xml', 'file_name': 'test.xml'},
            {'s3_key': 'folder/test.jpg', 'file_name': 'test.jpg'}
        ]
        request = request_factory.post(
            '/api/s3/process-uploads/',
            data={
                'folder_name': 'folder',
                'uploaded_files': uploaded_files
            },
            content_type='application/json'
        )
        force_authenticate(request, user=user)
        response = views.process_uploaded_files(request)
        
        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['processed_files']) == 2
        assert len(response.data['failed_files']) == 0
        
        # Verify the service was called correctly
        assert mock_instance.check_file_exists.call_count == 2
        mock_instance.get_object_content.assert_called_once_with('folder/test.xml')

    @patch('lacos.rest.views.UploadService')
    def test_process_uploaded_files_missing_params(self, mock_upload_service, request_factory):
        """Test processing uploaded files with missing parameters."""
        # Create a user for authentication
        user = MagicMock()
        user.is_authenticated = True
        
        # Make the request without required parameters
        request = request_factory.post(
            '/api/s3/process-uploads/',
            data={},
            content_type='application/json'
        )
        force_authenticate(request, user=user)
        response = views.process_uploaded_files(request)
        
        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['success'] is False
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.check_file_exists.assert_not_called()
        mock_instance.get_object_content.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_process_uploaded_files_file_not_found(self, mock_upload_service, request_factory):
        """Test processing uploaded files when a file is not found in S3."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.check_file_exists.return_value = False
        
        # Create a user for authentication
        user = MagicMock()
        user.is_authenticated = True
        
        # Make the request
        uploaded_files = [
            {'s3_key': 'folder/missing.xml', 'file_name': 'missing.xml'}
        ]
        request = request_factory.post(
            '/api/s3/process-uploads/',
            data={
                'folder_name': 'folder',
                'uploaded_files': uploaded_files
            },
            content_type='application/json'
        )
        force_authenticate(request, user=user)
        response = views.process_uploaded_files(request)
        
        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is False
        assert len(response.data['processed_files']) == 0
        assert len(response.data['failed_files']) == 1
        assert response.data['failed_files'][0]['error'] == 'File not found in S3'
        
        # Verify the service was called correctly
        mock_instance.check_file_exists.assert_called_once_with('folder/missing.xml')
        mock_instance.get_object_content.assert_not_called()

    @patch('lacos.rest.views.UploadService')
    def test_process_uploaded_files_invalid_json(self, mock_upload_service, request_factory):
        """Test processing uploaded files with invalid JSON."""
        # Create a user for authentication
        user = MagicMock()
        user.is_authenticated = True
        
        # Make the request with invalid JSON
        request = request_factory.post(
            '/api/s3/process-uploads/',
            data={
                'folder_name': 'folder',
                'uploaded_files': '{"invalid": json}'
            },
            content_type='application/json'
        )
        force_authenticate(request, user=user)
        response = views.process_uploaded_files(request)
        
        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['success'] is False
        assert 'error' in response.data
        assert 'Invalid uploaded_files JSON format' in response.data['error']
