from unittest.mock import Mock

import pytest

from lacos.storage.models import UploadSession, S3FileObject
from lacos.storage.services.upload_verification_service import UploadVerificationService


@pytest.mark.django_db
def test_verify_keys_marks_verified_and_completes_session(django_user_model):
    user = django_user_model.objects.create_user(username="verifier", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
    )
    file_obj = S3FileObject.objects.create(
        session=session,
        file_name="file.txt",
        s3_key="uploads/file.txt",
        file_size_bytes=0,
        content_type="text/plain",
    )

    upload_service = Mock()
    upload_service.mark_upload_complete.return_value = {
        "success": True,
        "exists": True,
        "s3_key": file_obj.s3_key,
        "file_size": 10,
        "content_type": "text/plain",
        "etag": "etag",
    }
    upload_service._format_size.return_value = "10 B"

    service = UploadVerificationService(upload_service=upload_service)
    result = service.verify_keys(
        [file_obj.s3_key],
        upload_session=session,
        bucket_name="test-bucket",
    )

    file_obj.refresh_from_db()
    session.refresh_from_db()

    assert file_obj.status == "verified"
    assert file_obj.file_size_bytes == 10
    assert file_obj.etag == "etag"
    assert session.status == "completed"
    assert session.completed_at is not None
    assert result["total_verified"] == 1
    assert result["total_failed"] == 0
    assert result["total_size"] == 10
    assert result["total_size_formatted"] == "10 B"


@pytest.mark.django_db
def test_verify_keys_marks_failed_and_session_failed(django_user_model):
    user = django_user_model.objects.create_user(username="verifier2", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
    )
    file_obj = S3FileObject.objects.create(
        session=session,
        file_name="missing.txt",
        s3_key="uploads/missing.txt",
    )

    upload_service = Mock()
    upload_service.mark_upload_complete.return_value = {
        "success": False,
        "exists": False,
        "s3_key": file_obj.s3_key,
        "error": "Not found",
    }
    upload_service._format_size.return_value = "0 B"

    service = UploadVerificationService(upload_service=upload_service)
    result = service.verify_keys(
        [file_obj.s3_key],
        upload_session=session,
        bucket_name="test-bucket",
    )

    file_obj.refresh_from_db()
    session.refresh_from_db()

    assert file_obj.status == "failed"
    assert file_obj.error_message == "Not found"
    assert session.status == "failed"
    assert session.completed_at is not None
    assert result["total_verified"] == 0
    assert result["total_failed"] == 1


@pytest.mark.django_db
def test_verify_keys_keeps_session_in_progress_until_all_files_done(django_user_model):
    user = django_user_model.objects.create_user(username="verifier3", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=2,
    )
    file_one = S3FileObject.objects.create(
        session=session,
        file_name="first.txt",
        s3_key="uploads/first.txt",
    )
    file_two = S3FileObject.objects.create(
        session=session,
        file_name="second.txt",
        s3_key="uploads/second.txt",
    )

    upload_service = Mock()
    upload_service.mark_upload_complete.return_value = {
        "success": True,
        "exists": True,
        "s3_key": file_one.s3_key,
        "file_size": 5,
        "content_type": "text/plain",
        "etag": "etag",
    }
    upload_service._format_size.return_value = "5 B"

    service = UploadVerificationService(upload_service=upload_service)
    service.verify_keys(
        [file_one.s3_key],
        upload_session=session,
        bucket_name="test-bucket",
    )

    session.refresh_from_db()
    file_one.refresh_from_db()
    file_two.refresh_from_db()

    assert file_one.status == "verified"
    assert file_two.status == "pending"
    assert session.status == "in_progress"
    assert session.completed_at is None
