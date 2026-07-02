from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from lacos.common.services.background_task_retention_service import (
    BackgroundTaskRetentionService,
)
from lacos.storage.models import BackgroundTask


def _make(task_name: str, age_days: float) -> BackgroundTask:
    row = BackgroundTask.objects.create(
        task_name=task_name, status=BackgroundTask.Status.SUCCESS
    )
    # created_at is auto-set; override it to simulate age.
    BackgroundTask.objects.filter(id=row.id).update(
        created_at=timezone.now() - timedelta(days=age_days)
    )
    return row


@pytest.mark.django_db
def test_deletes_rows_older_than_retention(settings):
    settings.BACKGROUND_TASK_RETENTION_DAYS = 30
    old = _make("periodic_upload_verification", 40)
    recent = _make("periodic_upload_verification", 5)
    newest = _make("periodic_upload_verification", 1)  # latest-per-task, always kept

    result = BackgroundTaskRetentionService().run()

    assert result["deleted"] == 1
    assert not BackgroundTask.objects.filter(id=old.id).exists()
    assert BackgroundTask.objects.filter(id=recent.id).exists()
    assert BackgroundTask.objects.filter(id=newest.id).exists()


@pytest.mark.django_db
def test_keeps_latest_row_per_task_even_if_old(settings):
    settings.BACKGROUND_TASK_RETENTION_DAYS = 30
    only_old = _make("rare_task", 90)  # old, but the only/most-recent for its task

    result = BackgroundTaskRetentionService().run()

    assert result["deleted"] == 0
    assert BackgroundTask.objects.filter(id=only_old.id).exists()


@pytest.mark.django_db
def test_no_old_rows_returns_zero(settings):
    settings.BACKGROUND_TASK_RETENTION_DAYS = 30
    _make("periodic_backup", 2)

    result = BackgroundTaskRetentionService().run()

    assert result["success"] is True
    assert result["deleted"] == 0
