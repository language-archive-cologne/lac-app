from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from lacos.storage.models import BackgroundTask
from lacos.users.tests.factories import UserFactory


@pytest.fixture
def superuser_client(client):
    user = UserFactory(is_superuser=True, is_staff=True)
    client.force_login(user)
    return client


@pytest.fixture
def non_superuser_client(client):
    user = UserFactory(is_superuser=False, is_staff=False)
    client.force_login(user)
    return client


@pytest.mark.django_db
@patch("lacos.dbadmin.views.transaction.on_commit")
def test_task_enqueue_creates_tracked_reindex_task(
    mock_on_commit,
    superuser_client,
):
    mock_task = MagicMock(return_value=SimpleNamespace(id="huey-123"))
    callbacks = []
    mock_on_commit.side_effect = callbacks.append

    with patch.dict(
        "lacos.dbadmin.views._TASK_CALLABLES",
        {"reindex_search_vectors_task": mock_task},
    ):
        response = superuser_client.post(
            reverse("dbadmin:task_enqueue", kwargs={"action": "reindex"}),
            HTTP_HX_REQUEST="true",
        )

    task = BackgroundTask.objects.get(task_name="blam_reindex_search_vectors")
    assert response.status_code == 200
    assert task.metadata["action"] == "reindex"
    assert task.metadata["source"] == "dbadmin"
    assert "task_id" not in task.metadata
    mock_task.assert_not_called()
    assert len(callbacks) == 1
    callbacks[0]()
    task.refresh_from_db()
    assert task.metadata["task_id"] == "huey-123"
    assert f"dbadmin-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
@patch("lacos.dbadmin.views.transaction.on_commit")
def test_task_enqueue_creates_tracked_collection_reindex_task(
    mock_on_commit,
    superuser_client,
):
    mock_task = MagicMock(return_value=SimpleNamespace(id="huey-456"))
    callbacks = []
    mock_on_commit.side_effect = callbacks.append

    with patch.dict(
        "lacos.dbadmin.views._TASK_CALLABLES",
        {"reindex_collections_task": mock_task},
    ):
        response = superuser_client.post(
            reverse(
                "dbadmin:task_enqueue",
                kwargs={"action": "reindex-collections"},
            ),
            HTTP_HX_REQUEST="true",
        )

    task = BackgroundTask.objects.get(task_name="blam_reindex_collections")
    assert response.status_code == 200
    assert task.metadata["action"] == "reindex-collections"
    assert task.metadata["source"] == "dbadmin"
    assert "task_id" not in task.metadata
    mock_task.assert_not_called()
    assert len(callbacks) == 1
    callbacks[0]()
    task.refresh_from_db()
    assert task.metadata["task_id"] == "huey-456"
    assert f"dbadmin-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
@patch("lacos.dbadmin.views.transaction.on_commit")
def test_task_enqueue_marks_failed_when_on_commit_enqueue_crashes(
    mock_on_commit,
    superuser_client,
):
    mock_task = MagicMock(side_effect=RuntimeError("queue failed"))
    callbacks = []
    mock_on_commit.side_effect = callbacks.append

    with patch.dict(
        "lacos.dbadmin.views._TASK_CALLABLES",
        {"backup_database_task": mock_task},
    ):
        response = superuser_client.post(
            reverse("dbadmin:task_enqueue", kwargs={"action": "backup"}),
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == 200
    task = BackgroundTask.objects.get(task_name="blam_database_backup")
    assert task.status == BackgroundTask.Status.QUEUED
    assert len(callbacks) == 1

    callbacks[0]()
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.FAILED
    assert "queue failed" in task.error


@pytest.mark.django_db
def test_task_enqueue_rejects_unknown_action(superuser_client):
    response = superuser_client.post(
        reverse("dbadmin:task_enqueue", kwargs={"action": "unknown"}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 400
    assert "Unknown task action." in response.content.decode()


@pytest.mark.django_db
def test_task_status_sets_success_trigger(superuser_client):
    task = BackgroundTask.objects.create(
        task_name="blam_reindex_search_vectors",
        status=BackgroundTask.Status.SUCCESS,
        message="Done",
    )

    response = superuser_client.get(
        reverse("dbadmin:task_status", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    trigger = json.loads(response["HX-Trigger"])
    assert trigger["showMessage"]["level"] == "success"


@pytest.mark.django_db
def test_task_enqueue_requires_superuser(non_superuser_client):
    response = non_superuser_client.post(
        reverse("dbadmin:task_enqueue", kwargs={"action": "reindex"}),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_background_task_mark_cancelled():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.RUNNING,
        message="Processing...",
    )
    task.mark_cancelled("Cancelled by admin")
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    assert task.message == "Cancelled by admin"
