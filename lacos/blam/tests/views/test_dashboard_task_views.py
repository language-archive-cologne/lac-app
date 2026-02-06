from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse

from lacos.storage.models import BackgroundTask


@pytest.fixture
def staff_client(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="staff-user",
        password="pass",
        is_staff=True,
    )
    client.force_login(user)
    return client


@pytest.fixture
def non_staff_client(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="non-staff-user",
        password="pass",
        is_staff=False,
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
@patch("lacos.blam.views.dashboard_task_views.reindex_search_vectors_task")
def test_dashboard_task_enqueue_creates_tracked_reindex_task(mock_task, staff_client):
    mock_task.return_value = SimpleNamespace(id="huey-123")

    response = staff_client.post(
        reverse("blam:dashboard_task_enqueue", kwargs={"action": "reindex"}),
        HTTP_HX_REQUEST="true",
    )

    task = BackgroundTask.objects.get(task_name="blam_reindex_search_vectors")
    assert response.status_code == 200
    assert task.metadata["action"] == "reindex"
    assert task.metadata["task_id"] == "huey-123"
    assert f"blam-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
@patch("lacos.blam.views.dashboard_task_views.reindex_collections_task")
def test_dashboard_task_enqueue_creates_tracked_collection_reindex_task(mock_task, staff_client):
    mock_task.return_value = SimpleNamespace(id="huey-456")

    response = staff_client.post(
        reverse("blam:dashboard_task_enqueue", kwargs={"action": "reindex-collections"}),
        HTTP_HX_REQUEST="true",
    )

    task = BackgroundTask.objects.get(task_name="blam_reindex_collections")
    assert response.status_code == 200
    assert task.metadata["action"] == "reindex-collections"
    assert task.metadata["task_id"] == "huey-456"
    assert f"blam-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
def test_dashboard_task_enqueue_rejects_unknown_action(staff_client):
    response = staff_client.post(
        reverse("blam:dashboard_task_enqueue", kwargs={"action": "unknown"}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 400
    assert "Unknown dashboard task action." in response.content.decode()


@pytest.mark.django_db
def test_dashboard_task_status_sets_success_trigger(staff_client):
    task = BackgroundTask.objects.create(
        task_name="blam_reindex_search_vectors",
        status=BackgroundTask.Status.SUCCESS,
        message="Done",
    )

    response = staff_client.get(
        reverse("blam:dashboard_task_status", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    trigger = json.loads(response["HX-Trigger"])
    assert trigger["showMessage"]["level"] == "success"


@pytest.mark.django_db
def test_dashboard_task_enqueue_requires_staff(non_staff_client):
    response = non_staff_client.post(
        reverse("blam:dashboard_task_enqueue", kwargs={"action": "reindex"}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 403
