import logging
from typing import Iterable, Optional, Set

from django.db.models import Count, Q
from django.utils import timezone

from lacos.storage.models import UploadSession, S3FileObject
from lacos.storage.services.upload_service import UploadService
from lacos.storage.services.folder_cache_service import FolderStructureCacheService

logger = logging.getLogger(__name__)


class UploadVerificationService:
    """Verify uploaded S3 objects and update per-file audit records."""

    def __init__(self, upload_service: Optional[UploadService] = None) -> None:
        self.upload_service = upload_service or UploadService()

    def verify_session(self, session: UploadSession) -> dict:
        """Verify all files in a session and update session status."""
        s3_keys = list(session.files.values_list("s3_key", flat=True))
        return self.verify_keys(
            s3_keys,
            upload_session=session,
            bucket_name=session.bucket_name,
        )

    def verify_keys(
        self,
        s3_keys: Iterable[str],
        *,
        upload_session: Optional[UploadSession] = None,
        bucket_name: Optional[str] = None,
    ) -> dict:
        """Verify the provided keys, optionally updating an UploadSession."""
        s3_keys = list(s3_keys)
        if not s3_keys:
            return {
                "success": False,
                "error": "No S3 keys provided",
                "results": [],
                "total_verified": 0,
                "total_failed": 0,
                "total_size": 0,
                "total_size_formatted": "0 B",
            }

        if upload_session and upload_session.bucket_name:
            bucket_name = upload_session.bucket_name

        results = []
        success = True
        total_verified = 0
        total_failed = 0
        total_size = 0

        for s3_key in s3_keys:
            logger.info("Verifying upload for S3 key: %s", s3_key)
            result = self.upload_service.mark_upload_complete(
                s3_key,
                bucket_name=bucket_name,
            )
            results.append(result)

            if upload_session:
                self._apply_result_to_session(upload_session, s3_key, result)

            if result.get("exists", False):
                total_verified += 1
                if "file_size" in result:
                    total_size += result["file_size"]
            else:
                total_failed += 1
                success = False

        total_size_formatted = self._format_size(total_size)

        if upload_session:
            self._update_session_status(upload_session)

        # Invalidate folder cache for affected paths
        if bucket_name and total_verified > 0:
            self._invalidate_affected_folders(bucket_name, s3_keys)

        # Enqueue media processing for verified audio files
        if upload_session and total_verified > 0:
            self._enqueue_media_processing(upload_session)

        return {
            "success": success,
            "results": results,
            "total_verified": total_verified,
            "total_failed": total_failed,
            "total_size": total_size,
            "total_size_formatted": total_size_formatted,
        }

    def _apply_result_to_session(
        self,
        session: UploadSession,
        s3_key: str,
        result: dict,
    ) -> None:
        file_qs = S3FileObject.objects.filter(session=session, s3_key=s3_key)
        if not file_qs.exists():
            logger.warning(
                "No S3FileObject found for session %s and key %s",
                session.id,
                s3_key,
            )
            return

        for file_obj in file_qs:
            if result.get("exists", False):
                file_obj.status = "verified"
                file_obj.upload_completed_at = timezone.now()
                etag = result.get("etag")
                if etag:
                    file_obj.etag = etag
                if "file_size" in result:
                    file_obj.file_size_bytes = result["file_size"]
                if result.get("content_type"):
                    file_obj.content_type = result["content_type"]
                file_obj.error_message = ""
            else:
                file_obj.status = "failed"
                file_obj.error_message = result.get(
                    "error",
                    "Upload verification failed",
                )
            file_obj.save()

    def _update_session_status(self, session: UploadSession) -> None:
        totals = session.files.aggregate(
            total=Count("id"),
            verified=Count("id", filter=Q(status="verified")),
            failed=Count("id", filter=Q(status="failed")),
        )
        total_files = totals["total"] or 0
        verified_files = totals["verified"] or 0
        failed_files = totals["failed"] or 0

        if total_files > 0 and (verified_files + failed_files) == total_files:
            session.status = "failed" if failed_files > 0 else "completed"
            session.completed_at = timezone.now()
        else:
            session.status = "in_progress"

        session.save(update_fields=["status", "completed_at"])

    def _format_size(self, size_bytes: int) -> str:
        try:
            return self.upload_service._format_size(size_bytes)
        except Exception as exc:  # pragma: no cover - fallback safety
            logger.warning("Failed to format size %s: %s", size_bytes, exc)
            return f"{size_bytes} B"

    def _enqueue_media_processing(self, session: UploadSession) -> None:
        """Enqueue audio sidecar generation for verified audio files in the session."""
        try:
            from lacos.explorer.media_utils import determine_media_type
            from lacos.storage.media_tasks import generate_peaks_task

            for file_obj in session.files.filter(status="verified"):
                media_type = determine_media_type(
                    file_obj.content_type, file_obj.file_name
                )
                if media_type == "audio":
                    bucket = file_obj.bucket_name or session.bucket_name
                    if bucket and file_obj.s3_key:
                        generate_peaks_task(bucket, file_obj.s3_key)
                        logger.info(
                            "Enqueued audio sidecar generation for %s/%s",
                            bucket,
                            file_obj.s3_key,
                        )
        except Exception as exc:
            logger.warning("Failed to enqueue media processing: %s", exc)

    def _invalidate_affected_folders(self, bucket_name: str, s3_keys: list) -> None:
        """Invalidate folder cache for all parent folders of uploaded files."""
        folder_paths: Set[str] = set()

        for s3_key in s3_keys:
            # Extract all parent folder paths from the s3_key
            parts = s3_key.rstrip("/").split("/")
            # Build paths: "", "folder1/", "folder1/folder2/", etc.
            folder_paths.add("")  # Root folder
            for i in range(1, len(parts)):
                folder_paths.add("/".join(parts[:i]) + "/")

        try:
            folder_cache = FolderStructureCacheService()
            folder_cache.invalidate_many(bucket_name, *folder_paths)
            logger.info(
                "Invalidated %d folder cache entries for bucket %s",
                len(folder_paths),
                bucket_name,
            )
        except Exception as exc:
            logger.warning(
                "Failed to invalidate folder cache for %s: %s",
                bucket_name,
                exc,
            )
