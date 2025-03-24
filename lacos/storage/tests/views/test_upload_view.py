import pytest
from unittest.mock import patch
from django.test import RequestFactory

from lacos.storage.views.upload_view import (
    upload_form,
    upload_success
)


@patch('lacos.storage.views.upload_view.render')
def test_upload_form(mock_render, prepared_request):
    """Test the upload form view."""
    request = prepared_request('/storage/upload/', method='get')
    upload_form(request)
    mock_render.assert_called_once_with(request, "upload/upload_form.html")


@patch('lacos.storage.views.upload_view.render')
def test_upload_success(mock_render, prepared_request):
    """Test the upload success view."""
    request = prepared_request('/storage/upload/success/', method='get')
    upload_success(request)
    mock_render.assert_called_once_with(request, "upload/upload_success.html")


