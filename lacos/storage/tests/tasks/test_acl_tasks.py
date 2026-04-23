from unittest.mock import patch

import pytest

from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.models import BackgroundTask
from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.tasks import load_collection_bundles_task


@pytest.mark.django_db
def test_load_collection_bundles_task_marks_running_and_persists_result():
    collection = Collection.objects.create(identifier="col-task")
    task_record = BackgroundTaskService.create(
        task_name="acl_load_collection_bundles",
        metadata={"collection_id": str(collection.pk), "mode": "missing"},
    )
    summary = {
        "collection_id": str(collection.pk),
        "collection_identifier": collection.identifier,
        "mode": "missing",
        "total": 3,
        "loaded": 2,
        "errors": 1,
        "failed_bundles": ["bundle-z"],
    }

    with patch(
        "lacos.storage.tasks.load_collection_bundle_acls",
        return_value=summary,
    ), patch(
        "lacos.storage.tasks.BackgroundTaskService.mark_running",
        wraps=BackgroundTaskService.mark_running,
    ) as mock_mark_running:
        result = load_collection_bundles_task.call_local(
            collection_id=str(collection.pk),
            mode="missing",
            tracking_id=str(task_record.id),
        )

    task_record.refresh_from_db()

    assert result["success"] is True
    assert result["loaded"] == 2
    assert result["errors"] == 1
    mock_mark_running.assert_called_once_with(
        str(task_record.id),
        message="Loading bundle ACLs",
    )
    assert task_record.status == BackgroundTask.Status.SUCCESS
    assert task_record.result["total"] == 3
    assert task_record.result["loaded"] == 2
    assert task_record.result["errors"] == 1
    assert "with 1 error" in task_record.message


@pytest.mark.django_db
def test_load_collection_bundles_task_marks_failed_on_top_level_error():
    collection = Collection.objects.create(identifier="col-fail")
    task_record = BackgroundTaskService.create(
        task_name="acl_load_collection_bundles",
        metadata={"collection_id": str(collection.pk), "mode": "all"},
    )

    with patch(
        "lacos.storage.tasks.load_collection_bundle_acls",
        side_effect=RuntimeError("boom"),
    ):
        result = load_collection_bundles_task.call_local(
            collection_id=str(collection.pk),
            mode="all",
            tracking_id=str(task_record.id),
        )

    task_record.refresh_from_db()

    assert result["success"] is False
    assert task_record.status == BackgroundTask.Status.FAILED
    assert "boom" in task_record.error
