"""Service to audit derivative (sidecar) status for audio files in S3."""

import logging
import time
from typing import Optional

from botocore.exceptions import (
    ConnectionClosedError,
    ConnectionError as BotoConnectionError,
    ConnectTimeoutError,
    EndpointConnectionError,
    HTTPClientError,
    ReadTimeoutError,
)
from django.conf import settings
from django.utils import timezone

from lacos.storage.models import DerivativeStatus
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


class DerivativeAuditConnectivityError(RuntimeError):
    """Raised when the audit cannot reach the S3 endpoint reliably."""


class DerivativeAuditService:
    """Scans S3 for WAV files and checks whether their derivatives exist."""

    DEFAULT_ARTIFACT_DELAY = 0.25
    DEFAULT_THROTTLE_DELAY = 0.1
    DEFAULT_THROTTLE_PAGE_DELAY = 1.0
    DEFAULT_CONNECTIVITY_BACKOFF_BASE = 1.0
    DEFAULT_CONNECTIVITY_BACKOFF_MAX = 30.0
    DEFAULT_MAX_CONSECUTIVE_CONNECTIVITY_FAILURES = 5

    def __init__(
        self,
        media_service: Optional[MediaProcessingService] = None,
    ) -> None:
        self.media_service = media_service or MediaProcessingService()
        # Pause between existence checks/files/pages to avoid overwhelming the S3 endpoint.
        self.artifact_delay = self._resolve_delay(
            "DERIVATIVE_AUDIT_ARTIFACT_DELAY_SECONDS",
            self.DEFAULT_ARTIFACT_DELAY,
        )
        self.throttle_delay = self._resolve_delay(
            "DERIVATIVE_AUDIT_FILE_DELAY_SECONDS",
            self.DEFAULT_THROTTLE_DELAY,
        )
        self.throttle_page_delay = self._resolve_delay(
            "DERIVATIVE_AUDIT_PAGE_DELAY_SECONDS",
            self.DEFAULT_THROTTLE_PAGE_DELAY,
        )
        self.connectivity_backoff_base = self._resolve_delay(
            "DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_BASE_SECONDS",
            self.DEFAULT_CONNECTIVITY_BACKOFF_BASE,
        )
        self.connectivity_backoff_max = self._resolve_delay(
            "DERIVATIVE_AUDIT_CONNECTIVITY_BACKOFF_MAX_SECONDS",
            self.DEFAULT_CONNECTIVITY_BACKOFF_MAX,
        )
        self.max_consecutive_connectivity_failures = self._resolve_int(
            "DERIVATIVE_AUDIT_MAX_CONSECUTIVE_CONNECTIVITY_FAILURES",
            self.DEFAULT_MAX_CONSECUTIVE_CONNECTIVITY_FAILURES,
        )

    def _resolve_delay(self, setting_name: str, default: float) -> float:
        raw_value = getattr(settings, setting_name, default)
        try:
            return max(0.0, float(raw_value))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s value %r. Falling back to %.3fs.",
                setting_name,
                raw_value,
                default,
            )
            return default

    def _resolve_int(self, setting_name: str, default: int) -> int:
        raw_value = getattr(settings, setting_name, default)
        try:
            return max(1, int(raw_value))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s value %r. Falling back to %d.",
                setting_name,
                raw_value,
                default,
            )
            return default

    def _sleep(self, delay: float) -> None:
        if delay > 0:
            time.sleep(delay)

    def _is_connectivity_error(self, exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                OSError,
                BotoConnectionError,
                ConnectTimeoutError,
                ConnectionClosedError,
                EndpointConnectionError,
                HTTPClientError,
                ReadTimeoutError,
                TimeoutError,
            ),
        )

    def _artifact_exists(self, bucket_name: str, key: str) -> bool:
        try:
            return self.media_service._artifact_exists(bucket_name, key)
        except Exception as exc:
            if self._is_connectivity_error(exc):
                raise DerivativeAuditConnectivityError(str(exc)) from exc
            raise

    def _connectivity_backoff_delay(self, consecutive_failures: int) -> float:
        exponent = max(0, consecutive_failures - 1)
        delay = self.connectivity_backoff_base * (2 ** exponent)
        return min(self.connectivity_backoff_max, delay)

    def _default_bucket_name(self) -> str:
        bucket_service = getattr(self.media_service, "bucket_service", None)
        configured_bucket = getattr(bucket_service, "production_bucket", None)
        if configured_bucket:
            return str(configured_bucket)

        aws_bucket = getattr(settings, "AWS_PRODUCTION_BUCKET_NAME", None)
        if aws_bucket:
            return str(aws_bucket)

        legacy_bucket = getattr(settings, "S3_PRODUCTION_BUCKET", None)
        if legacy_bucket:
            return str(legacy_bucket)

        return "lacos-production"

    def _log_audit_start(self, bucket_name: str, prefix: str) -> None:
        bucket_service = getattr(self.media_service, "bucket_service", None)
        logger.info(
            "Starting derivative audit",
            extra={
                "bucket_name": bucket_name,
                "prefix": prefix,
                "bucket_service_production_bucket": getattr(
                    bucket_service, "production_bucket", None
                ),
                "endpoint_url": getattr(bucket_service, "endpoint_url", None),
                "aws_production_bucket_name": getattr(
                    settings, "AWS_PRODUCTION_BUCKET_NAME", None
                ),
                "legacy_production_bucket": getattr(
                    settings, "S3_PRODUCTION_BUCKET", None
                ),
            },
        )

    def audit_bucket(
        self,
        bucket_name: Optional[str] = None,
        prefix: str = "",
    ) -> dict:
        """Scan *bucket_name* for WAV files and upsert DerivativeStatus rows.

        Returns a summary dict with counts.
        """
        bucket_name = bucket_name or self._default_bucket_name()
        self._log_audit_start(bucket_name, prefix)

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
        consecutive_connectivity_failures = 0
        aborted = False
        aborted_reason = None

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
                    consecutive_connectivity_failures = 0
                except DerivativeAuditConnectivityError as exc:
                    errors += 1
                    consecutive_connectivity_failures += 1
                    backoff_delay = self._connectivity_backoff_delay(
                        consecutive_connectivity_failures,
                    )
                    logger.warning(
                        "Connectivity failure auditing %s/%s (consecutive=%d): %s. Backing off for %.2fs.",
                        bucket_name,
                        key,
                        consecutive_connectivity_failures,
                        exc,
                        backoff_delay,
                    )
                    self._sleep(backoff_delay)
                    if (
                        consecutive_connectivity_failures
                        >= self.max_consecutive_connectivity_failures
                    ):
                        aborted = True
                        aborted_reason = (
                            "Aborted derivative audit after repeated S3 connectivity failures."
                        )
                        logger.error(
                            "%s bucket=%s prefix=%s consecutive_failures=%d",
                            aborted_reason,
                            bucket_name,
                            prefix or "/",
                            consecutive_connectivity_failures,
                        )
                        break
                except Exception:
                    logger.exception("Error auditing %s/%s", bucket_name, key)
                    errors += 1
                    consecutive_connectivity_failures = 0

                self._sleep(self.throttle_delay)

            if aborted:
                break

            self._sleep(self.throttle_page_delay)

        return {
            "success": errors == 0 and not aborted,
            "bucket_name": bucket_name,
            "prefix": prefix,
            "total_wav_files": scanned,
            "with_peaks": with_peaks,
            "with_spectrogram": with_spectrogram,
            "with_pitch": with_pitch,
            "missing_all_derivatives": missing_all,
            "errors": errors,
            "aborted": aborted,
            "error": aborted_reason,
        }

    def _check_and_upsert(
        self,
        bucket_name: str,
        s3_key: str,
        s3_obj: dict,
        now,
    ) -> DerivativeStatus:
        """Check derivative presence for a single WAV and upsert the row.

        The dashboard/status model tracks whether sidecar files exist in S3.
        Freshness is handled separately by generation paths that compare the
        stored source ETag metadata.
        """
        source_etag = s3_obj.get("ETag", "").strip('"')

        derivative_keys = (
            ("peaks_exists", self.media_service._peaks_key(s3_key)),
            (
                "spectrogram_exists",
                self.media_service._spectrogram_data_key(s3_key),
            ),
            ("pitch_exists", self.media_service._pitch_key(s3_key)),
        )
        derivative_flags: dict[str, bool] = {}

        for index, (field_name, derivative_key) in enumerate(derivative_keys):
            derivative_flags[field_name] = self._artifact_exists(
                bucket_name,
                derivative_key,
            )
            if index < len(derivative_keys) - 1:
                self._sleep(self.artifact_delay)

        status, _ = DerivativeStatus.objects.update_or_create(
            bucket_name=bucket_name,
            source_s3_key=s3_key,
            defaults={
                "source_etag": source_etag,
                **derivative_flags,
                "last_checked_at": now,
            },
        )
        return status
