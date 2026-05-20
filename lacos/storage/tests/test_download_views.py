"""Tests for download views."""

import json
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory

from lacos.storage.services.download_package_service import DownloadPackageTooLarge
from lacos.storage.services.download_script_service import DownloadInfo
from lacos.storage.services.resource_resolver_service import (
    ResolvedResource,
    ResourceError,
)
from lacos.storage.views.script_download_views import BundleScriptDownloadView
from lacos.storage.views.script_download_views import BundlePackageDownloadView


@pytest.fixture
def request_factory():
    """Create a Django RequestFactory."""
    return RequestFactory()


@pytest.fixture
def valid_altcha_payload():
    """Return a valid ALTCHA payload string."""
    return "eyJhbGdvcml0aG0iOiJTSEEtMjU2Iiwic2lnbmF0dXJlIjoiYWJjMTIzIn0="


@pytest.fixture
def valid_bundle_id():
    """Return a valid UUID string for bundle_id."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_resolved_resources():
    """Create sample resolved resources for testing."""
    return [
        ResolvedResource(
            resource_id="res-1",
            bucket="test-bucket",
            key="path/to/file1.wav",
            filename="file1.wav",
            size=1024,
            checksum="abc123",
            presigned_url="https://s3.example.com/file1?token=xyz",
        ),
        ResolvedResource(
            resource_id="res-2",
            bucket="test-bucket",
            key="path/to/file2.txt",
            filename="file2.txt",
            size=512,
            checksum=None,
            presigned_url="https://s3.example.com/file2?token=abc",
        ),
    ]


class TestBundleScriptDownloadView:
    """Tests for BundleScriptDownloadView."""

    @pytest.fixture
    def view(self):
        """Create view instance."""
        return BundleScriptDownloadView()

    def _make_request(self, request_factory, data):
        """Create a POST request with JSON body."""
        request = request_factory.post(
            "/storage/download/scripts/",
            data=json.dumps(data),
            content_type="application/json",
        )
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        return request

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_valid_request_returns_scripts(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
        sample_resolved_resources,
    ):
        """Test valid request returns all script formats."""
        # Setup mocks
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (sample_resolved_resources, [])
        mock_resolver_class.return_value = mock_resolver

        mock_bundle = MagicMock()
        mock_general_info = MagicMock()
        mock_general_info.display_title = "Test Bundle"
        mock_general_info.title = "Test Bundle"
        mock_bundle.get_general_info = mock_general_info
        mock_bundle.identifier = "test-bundle"
        mock_bundle_class.objects.get.return_value = mock_bundle

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1", "res-2"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["bundle_name"] == "Test Bundle"
        assert "expires_at" in data
        assert "bash" in data["scripts"]
        assert "powershell" in data["scripts"]
        assert "manifest" in data["scripts"]
        assert data["file_count"] == 2
        assert data["total_size"] == 1536  # 1024 + 512
        assert data["errors"] == []

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_invalid_bundle_id_returns_404(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test invalid bundle_id returns 404-style error."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        # Resolver returns bundle_not_found error for all resources
        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (
            [],
            [
                ResourceError(
                    resource_id="res-1",
                    error="bundle_not_found",
                    message=f"Bundle {valid_bundle_id} not found",
                ),
            ],
        )
        mock_resolver_class.return_value = mock_resolver

        # Bundle.DoesNotExist when looking up name
        from lacos.blam.models.bundle.bundle_repository import Bundle
        mock_bundle_class.DoesNotExist = Bundle.DoesNotExist
        mock_bundle_class.objects.get.side_effect = Bundle.DoesNotExist()

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 404
        assert data["success"] is False
        assert "not found" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_altcha_verification_failure_returns_403(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
    ):
        """Test ALTCHA verification failure returns 403."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (False, "Invalid signature")
        mock_altcha_service.return_value = mock_altcha

        request = self._make_request(request_factory, {
            "altcha": "invalid-payload",
            "bundle_id": "bundle-123",
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 403
        assert "Verification failed" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_too_many_resources_returns_400(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
    ):
        """Test too many resources returns 400."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        # Create more than MAX_RESOURCES
        resource_ids = [f"res-{i}" for i in range(101)]

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": "bundle-123",
            "resource_ids": resource_ids,
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Too many resources" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_rate_limiting(
        self,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
    ):
        """Test rate limiting returns 429."""
        mock_rate_limit.return_value = False

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": "bundle-123",
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 429
        assert "Too many requests" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_invalid_format_returns_400(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
    ):
        """Test invalid format returns 400."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": "bundle-123",
            "resource_ids": ["res-1"],
            "format": "invalid_format",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Invalid format" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_empty_resource_ids_returns_empty_scripts(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
    ):
        """Test empty resource_ids list returns empty response gracefully."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": "bundle-123",
            "resource_ids": [],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["file_count"] == 0
        assert data["total_size"] == 0
        assert data["scripts"] == {}

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_missing_altcha_returns_400(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
    ):
        """Test missing ALTCHA returns 400."""
        mock_rate_limit.return_value = True

        request = self._make_request(request_factory, {
            "bundle_id": "bundle-123",
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Missing ALTCHA" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_missing_bundle_id_returns_400(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
    ):
        """Test missing bundle_id returns 400."""
        mock_rate_limit.return_value = True

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Missing bundle_id" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_invalid_json_returns_400(
        self,
        mock_rate_limit,
        view,
        request_factory,
    ):
        """Test invalid JSON returns 400."""
        mock_rate_limit.return_value = True

        request = request_factory.post(
            "/storage/download/scripts/",
            data="not valid json",
            content_type="application/json",
        )
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "127.0.0.1"

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Invalid JSON" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_bash_only_format(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
        sample_resolved_resources,
    ):
        """Test bash-only format returns only bash script."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (sample_resolved_resources, [])
        mock_resolver_class.return_value = mock_resolver

        mock_bundle = MagicMock()
        mock_general_info = MagicMock()
        mock_general_info.display_title = "Test Bundle"
        mock_general_info.title = "Test Bundle"
        mock_bundle.get_general_info = mock_general_info
        mock_bundle.identifier = "test-bundle"
        mock_bundle_class.objects.get.return_value = mock_bundle

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1", "res-2"],
            "format": "bash",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert "bash" in data["scripts"]
        assert "powershell" not in data["scripts"]
        assert "manifest" not in data["scripts"]
        assert "#!/bin/bash" in data["scripts"]["bash"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_access_denied_returns_403(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test access denied error returns 403."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        # Resolver returns access_denied error
        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (
            [],
            [
                ResourceError(
                    resource_id="res-1",
                    error="access_denied",
                    message="Access denied to bundle resources",
                ),
            ],
        )
        mock_resolver_class.return_value = mock_resolver

        # Bundle.DoesNotExist when looking up name
        from lacos.blam.models.bundle.bundle_repository import Bundle
        mock_bundle_class.DoesNotExist = Bundle.DoesNotExist
        mock_bundle_class.objects.get.side_effect = Bundle.DoesNotExist()

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 403
        assert data["success"] is False
        assert "Access denied" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_partial_errors_included_in_response(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
        sample_resolved_resources,
    ):
        """Test partial errors are included in the response."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        # Return some resolved and some errors
        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (
            [sample_resolved_resources[0]],
            [
                ResourceError(
                    resource_id="res-2",
                    error="not_found",
                    message="Resource not found",
                ),
            ],
        )
        mock_resolver_class.return_value = mock_resolver

        mock_bundle = MagicMock()
        mock_general_info = MagicMock()
        mock_general_info.display_title = "Test Bundle"
        mock_general_info.title = "Test Bundle"
        mock_bundle.get_general_info = mock_general_info
        mock_bundle.identifier = "test-bundle"
        mock_bundle_class.objects.get.return_value = mock_bundle

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1", "res-2"],
            "format": "all",
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["file_count"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["resource_id"] == "res-2"
        assert data["errors"][0]["error"] == "not_found"


class TestBundlePackageDownloadView:
    """Tests for BundlePackageDownloadView."""

    @pytest.fixture
    def view(self):
        """Create view instance."""
        return BundlePackageDownloadView()

    def _make_request(self, request_factory, data):
        """Create a POST request with JSON body."""
        request = request_factory.post(
            "/storage/download/package/",
            data=json.dumps(data),
            content_type="application/json",
        )
        request.user = AnonymousUser()
        request.META["REMOTE_ADDR"] = "127.0.0.1"
        return request

    def test_package_endpoint_requires_csrf_token(self, valid_altcha_payload, valid_bundle_id):
        """Test package endpoint is not CSRF exempt."""
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            "/storage/download/package/",
            data=json.dumps({
                "altcha": valid_altcha_payload,
                "bundle_id": valid_bundle_id,
                "resource_ids": ["res-1"],
            }),
            content_type="application/json",
        )

        assert response.status_code == 403

    def test_script_endpoint_requires_csrf_token(self, valid_altcha_payload, valid_bundle_id):
        """Test script endpoint is not CSRF exempt."""
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            "/storage/download/scripts/",
            data=json.dumps({
                "altcha": valid_altcha_payload,
                "bundle_id": valid_bundle_id,
                "resource_ids": ["res-1"],
            }),
            content_type="application/json",
        )

        assert response.status_code == 403

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.DownloadPackageService")
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_valid_request_returns_tar_package(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        mock_package_service_class,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
        sample_resolved_resources,
    ):
        """Test valid package request returns a TAR attachment."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (sample_resolved_resources, [])
        mock_resolver_class.return_value = mock_resolver

        mock_bundle = MagicMock()
        mock_general_info = MagicMock()
        mock_general_info.display_title = "Test Bundle"
        mock_general_info.title = "Test Bundle"
        mock_bundle.get_general_info = mock_general_info
        mock_bundle.identifier = "test-bundle"
        mock_bundle_class.objects.get.return_value = mock_bundle

        archive = tempfile.TemporaryFile()
        archive.write(b"tar-bytes")
        archive.seek(0)
        mock_package_service = MagicMock()
        mock_package_service.create_tar_file.return_value = archive
        mock_package_service.archive_filename.return_value = "Test Bundle.tar"
        mock_package_service_class.return_value = mock_package_service

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1", "res-2"],
        })

        response = view.post(request)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/x-tar"
        assert 'filename="Test Bundle.tar"' in response["Content-Disposition"]
        assert response["X-Download-File-Count"] == "2"
        mock_package_service.create_tar_file.assert_called_once()
        assert mock_package_service.create_tar_file.call_args.kwargs["max_total_size"] == view.PACKAGE_SIZE_LIMIT

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_altcha_verification_failure_returns_403(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_bundle_id,
    ):
        """Test ALTCHA verification failure returns 403."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (False, "Invalid signature")
        mock_altcha_service.return_value = mock_altcha

        request = self._make_request(request_factory, {
            "altcha": "invalid-payload",
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1"],
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 403
        assert "Verification failed" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    def test_too_many_resources_returns_400(
        self,
        mock_altcha_service,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test package request enforces the resource count limit."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": [f"res-{i}" for i in range(101)],
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Too many resources" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_large_request_body_returns_413(
        self,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test package request enforces JSON body size limit."""
        mock_rate_limit.return_value = True
        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1"],
        })
        request.META["CONTENT_LENGTH"] = str(view.REQUEST_BODY_LIMIT + 1)

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 413
        assert "too large" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_non_object_json_returns_400(
        self,
        mock_rate_limit,
        view,
        request_factory,
    ):
        """Test package request rejects non-object JSON bodies."""
        mock_rate_limit.return_value = True
        request = self._make_request(request_factory, [])

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "Invalid JSON payload" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_multiple_selectors_returns_400(
        self,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test package request requires exactly one selector type."""
        mock_rate_limit.return_value = True
        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "collection_id": str(uuid.uuid4()),
            "resource_ids": ["res-1"],
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "exactly one" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    def test_invalid_resource_id_returns_400(
        self,
        mock_rate_limit,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
    ):
        """Test package request rejects malformed resource ids before resolution."""
        mock_rate_limit.return_value = True
        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": [""],
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert "resource_ids[0] is invalid" in data["error"]

    @pytest.mark.django_db
    @patch("lacos.storage.views.script_download_views.DownloadPackageService")
    @patch("lacos.storage.views.script_download_views.check_rate_limit")
    @patch("lacos.storage.views.script_download_views.get_altcha_service")
    @patch("lacos.storage.views.script_download_views.ResourceResolverService")
    @patch("lacos.storage.views.script_download_views.Bundle")
    def test_actual_package_size_limit_returns_413(
        self,
        mock_bundle_class,
        mock_resolver_class,
        mock_altcha_service,
        mock_rate_limit,
        mock_package_service_class,
        view,
        request_factory,
        valid_altcha_payload,
        valid_bundle_id,
        sample_resolved_resources,
    ):
        """Test actual S3 size limit errors map to 413."""
        mock_rate_limit.return_value = True
        mock_altcha = MagicMock()
        mock_altcha.verify_solution_base64.return_value = (True, None)
        mock_altcha_service.return_value = mock_altcha

        mock_resolver = MagicMock()
        mock_resolver.resolve_resources.return_value = (sample_resolved_resources, [])
        mock_resolver_class.return_value = mock_resolver

        mock_bundle = MagicMock()
        mock_bundle.get_general_info = None
        mock_bundle.identifier = "test-bundle"
        mock_bundle_class.objects.get.return_value = mock_bundle

        mock_package_service = MagicMock()
        mock_package_service.create_tar_file.side_effect = DownloadPackageTooLarge()
        mock_package_service_class.return_value = mock_package_service

        request = self._make_request(request_factory, {
            "altcha": valid_altcha_payload,
            "bundle_id": valid_bundle_id,
            "resource_ids": ["res-1", "res-2"],
        })

        response = view.post(request)
        data = json.loads(response.content)

        assert response.status_code == 413
        assert "Package is too large" in data["error"]
        assert data["detail"] == (
            "Maximum package size is 500 MB. "
            "Use the Scripts tab and run the generated script for larger downloads."
        )
