"""Tests for generate peaks dashboard views."""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import RequestFactory
from django.urls import reverse

from lacos.storage.permissions import ARCHIVIST_GROUP_NAME
from lacos.storage.views.generate_peaks_views import (
    generate_peaks_modal,
    GeneratePeaksView,
)


def _make_archivist(user):
    group, _ = Group.objects.get_or_create(name=ARCHIVIST_GROUP_NAME)
    user.groups.add(group)
    return user


# -- Permission tests --------------------------------------------------------

@pytest.mark.django_db
class TestPermissions:
    def test_modal_requires_archivist(self, client, django_user_model):
        user = django_user_model.objects.create_user("regular", "r@e.com", "pass")
        client.force_login(user)
        url = reverse("storage:generate_peaks_modal", kwargs={"bucket_name": "test"})
        assert client.get(url).status_code == 403

    def test_modal_allows_archivist(self, client, django_user_model):
        user = _make_archivist(
            django_user_model.objects.create_user("archivist", "a@e.com", "pass")
        )
        client.force_login(user)
        url = reverse("storage:generate_peaks_modal", kwargs={"bucket_name": "test"})
        response = client.get(url)
        assert response.status_code == 200

    def test_generate_requires_archivist(self, client, django_user_model):
        user = django_user_model.objects.create_user("regular", "r@e.com", "pass")
        client.force_login(user)
        url = reverse("storage:generate_peaks", kwargs={"bucket_name": "test"})
        assert client.post(url).status_code == 403


# -- Modal view tests --------------------------------------------------------

class TestGeneratePeaksModal:
    def test_renders_bucket_scope(self, prepared_request):
        request = prepared_request("/peaks/modal/my-bucket/", method="get")
        response = generate_peaks_modal(request, bucket_name="my-bucket")
        assert response.status_code == 200
        content = response.content.decode()
        assert "my-bucket" in content

    def test_renders_folder_scope(self, prepared_request):
        request = prepared_request("/peaks/modal/my-bucket/audio/", method="get")
        response = generate_peaks_modal(request, bucket_name="my-bucket", folder_path="audio/recordings")
        assert response.status_code == 200
        content = response.content.decode()
        assert "audio/recordings" in content
        assert "my-bucket" in content


# -- GeneratePeaksView tests -------------------------------------------------

class TestGeneratePeaksView:
    @patch("lacos.storage.views.generate_peaks_views.scan_and_generate_peaks_task")
    @patch("lacos.storage.views.generate_peaks_views.BackgroundTaskService")
    @patch("lacos.storage.views.generate_peaks_views.BucketService")
    def test_post_enqueues_background_task(
        self, MockBucketService, MockBGService, mock_scan_task, prepared_request
    ):
        MockBucketService.return_value.ensure_bucket_exists.return_value = True
        task_record = SimpleNamespace(
            id="12345678-1234-1234-1234-123456789abc",
            status="queued",
            task_name="generate_peaks",
            message="Queued",
            metadata={"bucket_name": "test-bucket", "folder_path": ""},
            created_at=None,
            result=None,
            error=None,
        )
        MockBGService.create.return_value = task_record
        mock_scan_task.return_value = MagicMock(id="huey-123")

        request = prepared_request("/peaks/generate/test-bucket/", method="post")
        response = GeneratePeaksView.as_view()(request, bucket_name="test-bucket")

        assert response.status_code == 200
        MockBGService.create.assert_called_once()
        mock_scan_task.assert_called_once_with(
            bucket_name="test-bucket",
            folder_path="",
            tracking_id=str(task_record.id),
            force=False,
        )

    @patch("lacos.storage.views.generate_peaks_views.scan_and_generate_peaks_task")
    @patch("lacos.storage.views.generate_peaks_views.BackgroundTaskService")
    @patch("lacos.storage.views.generate_peaks_views.BucketService")
    def test_post_with_folder_path(
        self, MockBucketService, MockBGService, mock_scan_task, prepared_request
    ):
        MockBucketService.return_value.ensure_bucket_exists.return_value = True
        task_record = SimpleNamespace(
            id="12345678-1234-1234-1234-123456789abd",
            status="queued",
            task_name="generate_peaks",
            message="Queued",
            metadata={"bucket_name": "b", "folder_path": "audio/wav"},
            created_at=None,
            result=None,
            error=None,
        )
        MockBGService.create.return_value = task_record
        mock_scan_task.return_value = MagicMock(id="huey-456")

        request = prepared_request("/peaks/generate/b/audio/wav/", method="post")
        response = GeneratePeaksView.as_view()(
            request, bucket_name="b", folder_path="audio/wav"
        )

        assert response.status_code == 200
        mock_scan_task.assert_called_once_with(
            bucket_name="b",
            folder_path="audio/wav",
            tracking_id=str(task_record.id),
            force=False,
        )

    @patch("lacos.storage.views.generate_peaks_views.BucketService")
    def test_post_invalid_bucket_returns_error(
        self, MockBucketService, prepared_request
    ):
        MockBucketService.return_value.ensure_bucket_exists.return_value = False

        request = prepared_request("/peaks/generate/bad-bucket/", method="post")
        response = GeneratePeaksView.as_view()(request, bucket_name="bad-bucket")

        assert response.status_code == 200
        content = response.content.decode()
        assert "alert-error" in content
        assert "not found" in content

    @patch("lacos.storage.views.generate_peaks_views.BucketService")
    def test_post_exception_returns_error_html(
        self, MockBucketService, prepared_request
    ):
        MockBucketService.return_value.ensure_bucket_exists.side_effect = Exception("S3 down")

        request = prepared_request("/peaks/generate/test/", method="post")
        response = GeneratePeaksView.as_view()(request, bucket_name="test")

        assert response.status_code == 200
        content = response.content.decode()
        assert "alert-error" in content
        assert "S3 down" in content

    @patch("lacos.storage.views.generate_peaks_views.scan_and_generate_peaks_task")
    @patch("lacos.storage.views.generate_peaks_views.BackgroundTaskService")
    @patch("lacos.storage.views.generate_peaks_views.BucketService")
    def test_post_sends_hx_trigger(
        self, MockBucketService, MockBGService, mock_scan_task, prepared_request
    ):
        MockBucketService.return_value.ensure_bucket_exists.return_value = True
        task_record = SimpleNamespace(
            id="12345678-1234-1234-1234-123456789abe",
            status="queued",
            task_name="generate_peaks",
            message="Queued",
            metadata={"bucket_name": "b", "folder_path": ""},
            created_at=None,
            result=None,
            error=None,
        )
        MockBGService.create.return_value = task_record
        mock_scan_task.return_value = MagicMock(id=None)

        request = prepared_request("/peaks/generate/b/", method="post")
        response = GeneratePeaksView.as_view()(request, bucket_name="b")

        assert response["HX-Trigger"] == "peaksGenerationStarted"
