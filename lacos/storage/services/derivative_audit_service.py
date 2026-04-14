"""Service to audit derivative (sidecar) status for audio files in S3."""

import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from lacos.storage.models import DerivativeStatus
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


class DerivativeAuditService:
    """Scans S3 for WAV files and checks whether their derivatives exist."""

    def __init__(
        self,
        media_service: Optional[MediaProcessingService] = None,
    ) -> None:
        self.media_service = media_service or MediaProcessingService()

    def audit_bucket(
        self,
        bucket_name: Optional[str] = None,
        prefix: str = "",
    ) -> dict:
        """Scan *bucket_name* for WAV files and upsert DerivativeStatus rows.

        Returns a summary dict with counts.
        """
        bucket_name = bucket_name or getattr(
            settings, "S3_PRODUCTION_BUCKET", "lacos-production"
        )

        s3_client = self.media_service.bucket_service.s3_client
        paginator = s3_client.get_paginator("list_objects_v2")

        page_kwargs: dict = {"Bucket": bucket_name}
        if prefix:
            normalized = prefix if prefix.endswith("/") else f"{prefix}/"
            page_kwargs["Prefix"] = normalized

        scanned = 0
        with_peaks = 0
        with_spectrogram = 0
        with_pitch = 0
        missing_all = 0
        errors = 0

        now = timezone.now()

        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.lower().endswith(".wav"):
                    continue

                scanned += 1
                try:
                    status = self._check_and_upsert(bucket_name, key, obj, now)
                    if status.peaks_exists:
                        with_peaks += 1
                    if status.spectrogram_exists:
                        with_spectrogram += 1
                    if status.pitch_exists:
                        with_pitch += 1
                    if not status.has_any_derivative:
                        missing_all += 1
                except Exception:
                    logger.exception("Error auditing %s/%s", bucket_name, key)
                    errors += 1

        return {
            "success": errors == 0,
            "bucket_name": bucket_name,
            "prefix": prefix,
            "total_wav_files": scanned,
            "with_peaks": with_peaks,
            "with_spectrogram": with_spectrogram,
            "with_pitch": with_pitch,
            "missing_all_derivatives": missing_all,
            "errors": errors,
        }

    def _check_and_upsert(
        self,
        bucket_name: str,
        s3_key: str,
        s3_obj: dict,
        now,
    ) -> DerivativeStatus:
        """Check derivative existence for a single WAV and upsert the row."""
        source_etag = s3_obj.get("ETag", "").strip('"')

        peaks = self.media_service._artifact_is_current(
            bucket_name, self.media_service._peaks_key(s3_key), source_etag
        )
        spectrogram = self.media_service._artifact_is_current(
            bucket_name, self.media_service._spectrogram_data_key(s3_key), source_etag
        )
        pitch = self.media_service._artifact_is_current(
            bucket_name, self.media_service._pitch_key(s3_key), source_etag
        )

        status, _ = DerivativeStatus.objects.update_or_create(
            bucket_name=bucket_name,
            source_s3_key=s3_key,
            defaults={
                "source_etag": source_etag,
                "peaks_exists": peaks,
                "spectrogram_exists": spectrogram,
                "pitch_exists": pitch,
                "last_checked_at": now,
            },
        )
        return status
