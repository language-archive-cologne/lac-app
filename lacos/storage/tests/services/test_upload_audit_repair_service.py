from unittest.mock import Mock

import pytest

from lacos.storage.models import UploadSession, S3FileObject
from lacos.storage.services.upload_audit_repair_service import UploadAuditRepairService


class StubUploadService:
    def _generate_file_key(self, file_name, path_prefix=None):
        if path_prefix:
            return f"{path_prefix}/{file_name}"
        return file_name


@pytest.mark.django_db
def test_build_expected_key_uses_original_path_and_folder_name(django_user_model):
    user = django_user_model.objects.create_user(username="auditor", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="imports",
        bucket_name="test-bucket",
        total_files=1,
    )
    file_obj = S3FileObject.objects.create(
        session=session,
        file_name="file.pdf",
        original_path="nested/path/file.pdf",
        s3_key="file.pdf",
    )

    service = UploadAuditRepairService(
        bucket_service=Mock(),
        upload_service=StubUploadService(),
    )

    expected = service.build_expected_key(file_obj)
    assert expected == "imports/nested/path/file.pdf"


@pytest.mark.django_db
def test_repair_file_object_updates_key_when_object_exists(django_user_model):
    user = django_user_model.objects.create_user(username="auditor2", password="pass")
    session = UploadSession.objects.create(
        user=user,
        folder_name="uploads",
        bucket_name="test-bucket",
        total_files=1,
    )
    file_obj = S3FileObject.objects.create(
        session=session,
        file_name="sample.txt",
        original_path="folder/sample.txt",
        s3_key="sample.txt",
    )

    bucket_service = Mock()
    bucket_service.get_file_info.return_value = {
        "success": True,
        "file_size": 123,
        "content_type": "text/plain",
        "etag": '"etag"',
    }

    service = UploadAuditRepairService(
        bucket_service=bucket_service,
        upload_service=StubUploadService(),
    )

    result = service.repair_file_object(file_obj)
    file_obj.refresh_from_db()

    assert result.status == "updated"
    assert file_obj.s3_key == "uploads/folder/sample.txt"
    assert file_obj.file_size_bytes == 123
    assert file_obj.content_type == "text/plain"
    assert file_obj.etag == "etag"
