import pytest
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import force_authenticate

from lacos.rest.views.processing_views import process_uploaded_files


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


class TestProcessingViews:
    """Test cases for the processing-related views."""

    @patch('lacos.rest.views.processing_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.processing_views.UploadService')
    def test_process_uploaded_files_success(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test successful processing of uploaded files."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.check_file_exists.return_value = True
        mock_instance.get_object_content.return_value = "<xml>Test content</xml>"

        # Make the request
        uploaded_files = [
            {'s3_key': 'folder/test1.xml', 'file_name': 'test1.xml'},
            {'s3_key': 'folder/test2.jpg', 'file_name': 'test2.jpg'}
        ]
        
        request = request_factory.post(
            '/api/process-uploaded-files/', 
            data={
                'folder_name': 'folder',
                'uploaded_files': uploaded_files
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = process_uploaded_files(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['processed_files']) == 2
        assert len(response.data['failed_files']) == 0
        
        # Verify XML file was processed correctly
        xml_file = next(f for f in response.data['processed_files'] if f['file_name'] == 'test1.xml')
        assert xml_file['status'] == 'Processed as XML'
        
        # Verify non-XML file was stored correctly
        jpg_file = next(f for f in response.data['processed_files'] if f['file_name'] == 'test2.jpg')
        assert jpg_file['status'] == 'Stored in S3'
        
        # Verify the service was called with correct parameters
        mock_instance.check_file_exists.assert_any_call('folder/test1.xml')
        mock_instance.check_file_exists.assert_any_call('folder/test2.jpg')
        mock_instance.get_object_content.assert_called_once_with('folder/test1.xml')

    @patch('lacos.rest.views.processing_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.processing_views.UploadService')
    def test_process_uploaded_files_missing_params(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test processing uploaded files with missing parameters."""
        # Make the request with missing uploaded_files
        request = request_factory.post(
            '/api/process-uploaded-files/',
            data={'folder_name': 'folder'},
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = process_uploaded_files(request)

        # Assert response
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert 'Missing required parameters' in response.data['error']
        
        # Make sure the service was not called
        mock_instance = mock_upload_service.return_value
        mock_instance.check_file_exists.assert_not_called()

    @patch('lacos.rest.views.processing_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.processing_views.UploadService')
    def test_process_uploaded_files_nonexistent_file(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test processing uploaded files where one file doesn't exist in S3."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        # First file exists, second doesn't
        mock_instance.check_file_exists.side_effect = [True, False]
        mock_instance.get_object_content.return_value = "<xml>Test content</xml>"

        # Make the request
        uploaded_files = [
            {'s3_key': 'folder/test1.xml', 'file_name': 'test1.xml'},
            {'s3_key': 'folder/test2.jpg', 'file_name': 'test2.jpg'}
        ]
        
        request = request_factory.post(
            '/api/process-uploaded-files/', 
            data={
                'folder_name': 'folder',
                'uploaded_files': uploaded_files
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = process_uploaded_files(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is True
        assert len(response.data['processed_files']) == 1
        assert len(response.data['failed_files']) == 1
        
        # Verify the successful file was processed
        assert response.data['processed_files'][0]['file_name'] == 'test1.xml'
        
        # Verify the failed file was reported
        assert response.data['failed_files'][0]['file_name'] == 'test2.jpg'
        assert 'File not found in S3' in response.data['failed_files'][0]['error']

    @patch('lacos.rest.views.processing_views.build_legacy_upload_denied_response', return_value=None)
    @patch('lacos.rest.views.processing_views.UploadService')
    def test_process_uploaded_files_processing_error(self, mock_upload_service, mock_access_check, request_factory, authenticated_user):
        """Test handling of errors during file processing."""
        # Configure the mock
        mock_instance = MagicMock()
        mock_upload_service.return_value = mock_instance
        mock_instance.check_file_exists.return_value = True
        mock_instance.get_object_content.side_effect = Exception("XML parsing error")

        # Make the request
        uploaded_files = [
            {'s3_key': 'folder/test1.xml', 'file_name': 'test1.xml'}
        ]
        
        request = request_factory.post(
            '/api/process-uploaded-files/', 
            data={
                'folder_name': 'folder',
                'uploaded_files': uploaded_files
            },
            content_type='application/json'
        )
        force_authenticate(request, user=authenticated_user)
        response = process_uploaded_files(request)

        # Assert response
        assert response.status_code == status.HTTP_200_OK
        assert response.data['success'] is False  # No files were processed successfully
        assert len(response.data['processed_files']) == 0
        assert len(response.data['failed_files']) == 1
        
        # Verify the error was reported
        assert response.data['failed_files'][0]['file_name'] == 'test1.xml'
        assert 'XML parsing error' in response.data['failed_files'][0]['error'] 
