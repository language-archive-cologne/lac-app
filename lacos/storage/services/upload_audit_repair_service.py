import logging
from dataclasses import dataclass
from typing import Optional

from lacos.storage.models import S3FileObject
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.upload_service import UploadService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepairResult:
    status: str
    s3_key: Optional[str] = None
    expected_key: Optional[str] = None
    error: Optional[str] = None


class UploadAuditRepairService:
    """Repair S3FileObject keys using upload metadata and S3 lookups."""

    def __init__(
        self,
        *,
        bucket_service: Optional[BucketService] = None,
        upload_service: Optional[UploadService] = None,
    ) -> None:
        self.bucket_service = bucket_service or BucketService(skip_bucket_check=True)
        self.upload_service = upload_service or UploadService()

    def build_expected_key(self, file_obj: S3FileObject) -> Optional[str]:
        file_name = (file_obj.file_name or "").strip()
        if not file_name:
            return None

        file_path = (file_obj.original_path or "").strip()
        session = file_obj.session
        effective_path_prefix = (session.folder_name or "").strip() if session else ""

        if file_path:
            if file_path.endswith(file_name):
                file_path = file_path[: -len(file_name)].rstrip("/")
            if file_path:
                effective_path_prefix = (
                    f"{effective_path_prefix}/{file_path}" if effective_path_prefix else file_path
                )

        return self.upload_service._generate_file_key(file_name, effective_path_prefix)

    def repair_file_object(
        self,
        file_obj: S3FileObject,
        *,
        bucket_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> RepairResult:
        expected_key = self.build_expected_key(file_obj)
        if not expected_key:
            return RepairResult(status="skipped", error="missing_expected_key")

        if expected_key == file_obj.s3_key:
            return RepairResult(status="unchanged", s3_key=file_obj.s3_key)

        session = file_obj.session
        target_bucket = bucket_name or getattr(session, "bucket_name", None)
        if not target_bucket:
            return RepairResult(
                status="skipped",
                expected_key=expected_key,
                error="missing_bucket",
            )

        info = self.bucket_service.get_file_info(target_bucket, expected_key)
        if not info.get("success"):
            return RepairResult(
                status="missing",
                expected_key=expected_key,
                error=info.get("error"),
            )

        if not dry_run:
            file_obj.s3_key = expected_key
            if info.get("file_size") is not None:
                file_obj.file_size_bytes = info["file_size"]
            if info.get("content_type"):
                file_obj.content_type = info["content_type"]
            etag = info.get("etag")
            if etag:
                file_obj.etag = etag.strip('"')
            file_obj.save()

        return RepairResult(status="updated", s3_key=expected_key)
