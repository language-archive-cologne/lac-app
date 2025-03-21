import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import force_authenticate

from lacos.rest.views.object_views import copy_object


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


class TestObjectViews:
    """Test cases for the object-related views."""

    @patch('lacos.rest.views.object_views.UploadService')
    def test_copy_object_success(self, mock_upload_service, request_factory, authenticated_user):
        """Test successful copying of an object."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.copy_object.return_value = {
            'success': True,
            'source_key': 'source/test.jpg',
            'dest_key': 'destination/test.jpg',
            'etag': '123456789abcdef',
            'size': 12345,
            'content_type': 'image/jpeg'
        }

        # Make the request
        request = request_factory.post(
            '/api/copy-object/', 
            data={
                'source_key': 'source/test.jpg',
                'dest_key': 'destination/test.jpg',
                'source_bucket': 'source-bucket',
                'dest_bucket': 'dest-bucket'
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = copy_object(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert response.data['source_key'] == 'source/test.jpg'
        assert response.data['dest_key'] == 'destination/test.jpg'
        assert response.data['etag'] == '123456789abcdef'
        
        # Verify the service was called with correct parameters
        mock_instance.copy_object.assert_called_once_with(
            source_key='source/test.jpg',
            dest_key='destination/test.jpg',
            source_bucket='source-bucket',
            dest_bucket='dest-bucket'
        )

    @patch('lacos.rest.views.object_views.UploadService')
    def test_copy_object_missing_params(self, mock_upload_service, request_factory, authenticated_user):
        """Test copying an object with missing parameters."""
        # Make the request with missing dest_key
        request = request_factory.post(
            '/api/copy-object/',
            data={'source_key': 'source/test.jpg'},
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = copy_object(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.copy_object.assert_not_called()

    @patch('lacos.rest.views.object_views.UploadService')
    def test_copy_object_service_error(self, mock_upload_service, request_factory, authenticated_user):
        """Test handling of service errors when copying an object."""
        # Configure the mock to return an error
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.copy_object.return_value = {
            'success': False,
            'error': 'Source object not found',
            'source_key': 'source/test.jpg',
            'dest_key': 'destination/test.jpg'
        }

        # Make the request
        request = request_factory.post(
            '/api/copy-object/',
            data={
                'source_key': 'source/test.jpg',
                'dest_key': 'destination/test.jpg'
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = copy_object(request)

        # Assert response
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data['success'] is False
        assert response.data['error'] == 'Source object not found' 