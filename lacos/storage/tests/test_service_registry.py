import types

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from lacos.storage.services import registry
from lacos.storage.services.base_storage_service import BaseStorageService


@pytest.fixture(autouse=True)
def reset_registry():
    registry.reset_storage_services()
    yield
    registry.reset_storage_services()


def _install_fake_s3(monkeypatch, buckets=None, list_buckets_calls=None):
    buckets = buckets or ["demo-bucket"]

    class StubS3Client:
        def list_buckets(self):
            if list_buckets_calls is not None:
                list_buckets_calls.append(True)
            return {"Buckets": [{"Name": name} for name in buckets]}

    monkeypatch.setattr(BaseStorageService, "_create_s3_client", lambda self: StubS3Client())
    monkeypatch.setattr(BaseStorageService, "_is_minio_environment", lambda self: False)


def test_bucket_service_cached_singleton(monkeypatch):
    fetch_calls: list[bool] = []

    def fake_lazy_fetch(self):
        fetch_calls.append(True)
        return (bucket for bucket in ["demo-bucket", "archive-bucket"])

    monkeypatch.setattr(BaseStorageService, "_lazy_fetch_buckets", fake_lazy_fetch)
    _install_fake_s3(monkeypatch)

    service_a = registry.get_bucket_service()
    first = service_a.get_all_accessible_buckets(force_refresh=True)
    second = service_a.get_all_accessible_buckets()
    service_b = registry.get_bucket_service()

    assert service_a is service_b
    assert first == second == ["demo-bucket", "archive-bucket"]
    assert len(fetch_calls) == 1


@pytest.mark.django_db
def test_dashboard_prefetch_hits_cache(monkeypatch, client, settings):
    settings.S3_WORKSPACE_BUCKETS = []
    fetch_calls: list[bool] = []

    def fake_lazy_fetch(self):
        fetch_calls.append(True)
        return (name for name in ["workspace-bucket"])

    monkeypatch.setattr(BaseStorageService, "_lazy_fetch_buckets", fake_lazy_fetch)
    _install_fake_s3(monkeypatch, buckets=["workspace-bucket"])

    user = get_user_model().objects.create_user(username="dashboarder", password="secret")
    client.force_login(user)

    url = reverse("storage:archivist_dashboard")
    response_first = client.get(url)
    assert response_first.status_code == 200

    response_second = client.get(url)
    assert response_second.status_code == 200
    assert len(fetch_calls) == 1


def test_huey_task_reuses_bucket_service(monkeypatch):
    monkeypatch.setattr(BaseStorageService, "_lazy_fetch_buckets", lambda self: (name for name in ["huey-bucket"]))
    _install_fake_s3(monkeypatch, buckets=["huey-bucket"])
    monkeypatch.setattr(BaseStorageService, "_is_minio_environment", lambda self: False)

    from lacos.storage import tasks

    class StubOCFLService:
        def __init__(self, bucket_service):
            self.bucket_service = bucket_service

        def analyze_folder_structure(self, bucket_name, folder_path):
            return {"success": True, "structure_analysis": {}}

    class StubBackgroundTaskService:
        @staticmethod
        def mark_running(*args, **kwargs):
            return None

        @staticmethod
        def mark_success(*args, **kwargs):
            return None

        @staticmethod
        def mark_failed(*args, **kwargs):
            return None

        @staticmethod
        def touch(*args, **kwargs):
            return None

    monkeypatch.setattr(tasks, "OCFLService", StubOCFLService)
    monkeypatch.setattr(tasks, "BackgroundTaskService", StubBackgroundTaskService)

    service_ids: list[int] = []

    def tracking_get_bucket_service(*args, **kwargs):
        service = registry.get_bucket_service(*args, **kwargs)
        service_ids.append(id(service))
        return service

    monkeypatch.setattr(tasks, "get_bucket_service", tracking_get_bucket_service)

    result_one = tasks.analyze_folder_for_ocfl_task.call_local("huey-bucket", "folder-a")
    result_two = tasks.analyze_folder_for_ocfl_task.call_local("huey-bucket", "folder-b")

    assert result_one["success"] is True
    assert result_two["success"] is True
    assert len(set(service_ids)) == 1
