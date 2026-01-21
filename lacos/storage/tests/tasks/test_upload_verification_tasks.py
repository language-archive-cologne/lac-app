from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from lacos.storage.models import UploadSession, S3FileObject
from lacos.storage.tasks import verify_upload_session_task
from lacos.storage.upload_verification_tasks import verify_pending_upload_sessions


@pytest.mark.django_db
@patch("lacos.storage.upload_verification_tasks.UploadVerificationService")
def test_verify_upload_session_task_runs_service(mock_service, django_user_model):
    user = django_user_model.objects.create_user(username="taskuser", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
    )
    S3FileObject.objects.create(
        session=session,
        file_name="file.txt",
        s3_key="uploads/file.txt",
    )

    service_instance = mock_service.return_value
    service_instance.verify_session.return_value = {"success": True}

    result = verify_upload_session_task.call_local(str(session.id))

    service_instance.verify_session.assert_called_once_with(session)
    assert result["success"] is True


@pytest.mark.django_db
@patch("lacos.storage.upload_verification_tasks.UploadVerificationService")
def test_verify_pending_upload_sessions_checks_stale_sessions(mock_service, settings, django_user_model):
    settings.UPLOAD_VERIFICATION_GRACE_SECONDS = 0

    user = django_user_model.objects.create_user(username="staleuser", password="pass")
    stale_session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
        status="in_progress",
    )
    UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
        status="completed",
    )

    UploadSession.objects.filter(id=stale_session.id).update(
        created_at=timezone.now() - timedelta(hours=1),
    )

    service_instance = mock_service.return_value
    service_instance.verify_session.return_value = {"success": True}

    runner = getattr(verify_pending_upload_sessions, "call_local", verify_pending_upload_sessions)
    result = runner()

    service_instance.verify_session.assert_called_once()
    assert result["sessions_checked"] == 1
