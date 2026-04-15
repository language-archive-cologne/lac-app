from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse

from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService
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
def test_task_enqueue_creates_tracked_derivative_audit_task(
    mock_on_commit,
    superuser_client,
):
    mock_task = MagicMock(return_value=SimpleNamespace(id="huey-789"))
    callbacks = []
    mock_on_commit.side_effect = callbacks.append

    with patch.dict(
        "lacos.dbadmin.views._TASK_CALLABLES",
        {"audit_derivatives_task": mock_task},
    ):
        response = superuser_client.post(
            reverse(
                "dbadmin:task_enqueue",
                kwargs={"action": "audit-derivatives"},
            ),
            HTTP_HX_REQUEST="true",
        )

    task = BackgroundTask.objects.get(task_name="audit_derivatives")
    assert response.status_code == 200
    assert task.metadata["action"] == "audit-derivatives"
    assert task.metadata["source"] == "dbadmin"
    assert "task_id" not in task.metadata
    mock_task.assert_not_called()
    assert len(callbacks) == 1
    callbacks[0]()
    task.refresh_from_db()
    assert task.metadata["task_id"] == "huey-789"
    assert f"dbadmin-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
def test_scheduled_tasks_view_shows_disabled_derivative_audit(superuser_client):
    response = superuser_client.get(
        reverse("dbadmin:scheduled_tasks"),
        HTTP_HX_REQUEST="true",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Derivative Audit" in content
    assert "disabled" in content.lower()
    assert "Automatic scheduling disabled while S3 throttling is being validated." in content


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


@pytest.mark.django_db
def test_cancel_queued_task_revokes_huey_and_marks_cancelled():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
        huey_task_id="huey-abc",
    )
    with patch("lacos.storage.services.background_task_service.revoke_by_id") as mock_revoke:
        BackgroundTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    assert "Cancelled" in task.message
    mock_revoke.assert_called_once_with("huey-abc")


@pytest.mark.django_db
def test_cancel_running_task_marks_cancelled_without_huey_revoke():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.RUNNING,
        huey_task_id="huey-def",
    )
    with patch("lacos.storage.services.background_task_service.revoke_by_id") as mock_revoke:
        BackgroundTaskService.cancel(task)
    task.refresh_from_db()
    assert task.status == BackgroundTask.Status.CANCELLED
    mock_revoke.assert_not_called()


@pytest.mark.django_db
def test_cancel_completed_task_raises_value_error():
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.SUCCESS,
    )
    with pytest.raises(ValueError, match="Cannot cancel"):
        BackgroundTaskService.cancel(task)


@pytest.mark.django_db
def test_task_cancel_view_cancels_queued_task(superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
    )
    with patch("lacos.dbadmin.views.BackgroundTaskService.cancel"):
        response = superuser_client.post(
            reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
            HTTP_HX_REQUEST="true",
        )
    assert response.status_code == 200
    assert f"dbadmin-task-{task.id}" in response.content.decode()


@pytest.mark.django_db
def test_task_cancel_view_returns_error_for_completed_task(superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.SUCCESS,
    )
    response = superuser_client.post(
        reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_task_cancel_view_requires_superuser(non_superuser_client):
    task = BackgroundTask.objects.create(
        task_name="test_task",
        status=BackgroundTask.Status.QUEUED,
    )
    response = non_superuser_client.post(
        reverse("dbadmin:task_cancel", kwargs={"task_id": task.id}),
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
