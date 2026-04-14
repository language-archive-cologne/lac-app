"""Huey tasks for media processing (audio sidecar generation)."""

import errno
import logging

from huey.contrib.djhuey import db_task

from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


@db_task(retries=1, retry_delay=60)
def scan_and_generate_peaks_task(
    bucket_name: str, folder_path: str = "", tracking_id: str | None = None,
    force: bool = False,
) -> dict:
    """Scan a bucket/folder for audio files and enqueue sidecar generation.

    Runs as a background task so the HTTP request returns immediately.
    Individual files are dispatched to generate_peaks_task which handles
    ETag-based idempotency (stale peaks are regenerated).
    """
    from lacos.storage.services.bucket_service import BucketService

    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Scanning for audio files")

    bucket_service = BucketService()
    paginator = bucket_service.s3_client.get_paginator("list_objects_v2")

    page_kwargs = {"Bucket": bucket_name}
    prefix = folder_path
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    if prefix:
        page_kwargs["Prefix"] = prefix

    enqueued = 0
    scanned = 0

    try:
        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.lower().endswith(".wav"):
                    continue
                scanned += 1
                generate_peaks_task(bucket_name, key, force=force)
                enqueued += 1
    except Exception as exc:
        msg = f"Scan failed after enqueueing {enqueued} of {scanned} audio files: {exc}"
        logger.error(msg)
        if tracking_id:
            BackgroundTaskService.mark_failed(tracking_id, error_message=msg)
        return {"success": False, "error": msg, "enqueued": enqueued}

    result = {"success": True, "enqueued": enqueued, "audio_files": scanned}

    if tracking_id:
        if enqueued == 0:
            message = "No audio files found" if scanned == 0 else "No new audio files to process"
        else:
            message = f"Enqueued {enqueued} audio files for sidecar generation"
        BackgroundTaskService.mark_success(
            tracking_id, message=message, result=result,
        )

    logger.info(
        "Peaks scan complete for %s/%s: enqueued=%d audio_files=%d",
        bucket_name, folder_path or "(root)", enqueued, scanned,
    )
    return result


@db_task(retries=2, retry_delay=120)
def generate_peaks_task(
    bucket_name: str, s3_key: str, tracking_id: str | None = None,
    force: bool = False,
) -> dict:
    """Generate audio sidecars (peaks + spectrogram) for a single audio file."""
    logger.info("Generating audio sidecars for %s/%s", bucket_name, s3_key)

    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Generating audio sidecars")

    service = MediaProcessingService()
    try:
        result = service.generate_peaks(bucket_name, s3_key, force=force)
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            result = {
                "success": False,
                "error_code": "no_space",
                "error": "No space left on device while generating peaks sidecars",
            }
        else:
            raise
    except Exception as exc:
        if "No space left on device" in str(exc):
            result = {
                "success": False,
                "error_code": "no_space",
                "error": f"No space left on device while generating peaks sidecars: {exc}",
            }
        else:
            raise

    if tracking_id:
        if result.get("success"):
            BackgroundTaskService.mark_success(
                tracking_id,
                message="Audio sidecars generated",
                result={
                    "peaks_key": result.get("peaks_key"),
                    "spectrogram_data_key": result.get("spectrogram_data_key"),
                },
            )
        else:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=result.get("error", "Unknown error"),
            )

    if result.get("success"):
        _update_derivative_status(bucket_name, s3_key, result)
    else:
        logger.error(
            "Audio sidecar generation failed for %s/%s: %s",
            bucket_name,
            s3_key,
            result.get("error"),
        )

    return result


def _update_derivative_status(bucket_name: str, s3_key: str, result: dict) -> None:
    """Upsert DerivativeStatus after successful peak generation."""
    try:
        from django.utils import timezone
        from lacos.storage.models import DerivativeStatus

        DerivativeStatus.objects.update_or_create(
            bucket_name=bucket_name,
            source_s3_key=s3_key,
            defaults={
                "source_etag": result.get("source_etag", ""),
                "peaks_exists": bool(result.get("peaks_key")),
                "spectrogram_exists": bool(result.get("spectrogram_data_key")),
                "pitch_exists": bool(result.get("pitch_key")),
                "last_checked_at": timezone.now(),
            },
        )
    except Exception:
        logger.exception(
            "Failed to update DerivativeStatus for %s/%s", bucket_name, s3_key
        )
