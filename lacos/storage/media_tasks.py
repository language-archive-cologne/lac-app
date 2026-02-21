"""Huey tasks for media processing (audio sidecar generation)."""

import logging

from huey.contrib.djhuey import db_task

from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


@db_task(retries=1, retry_delay=60)
def scan_and_generate_peaks_task(
    bucket_name: str, folder_path: str = "", tracking_id: str | None = None
) -> dict:
    """Scan a bucket/folder for audio files and enqueue sidecar generation.

    Runs as a background task so the HTTP request returns immediately.
    Individual files are dispatched to generate_peaks_task which handles
    ETag-based idempotency (stale peaks are regenerated).
    """
    from lacos.explorer.media_utils import determine_media_type
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
                if (
                    key.endswith(".peaks.json")
                    or key.endswith(".spectrogram.json")
                ):
                    continue
                if determine_media_type(None, key) != "audio":
                    continue
                scanned += 1
                generate_peaks_task(bucket_name, key)
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
    bucket_name: str, s3_key: str, tracking_id: str | None = None
) -> dict:
    """Generate audio sidecars (peaks + spectrogram) for a single audio file."""
    logger.info("Generating audio sidecars for %s/%s", bucket_name, s3_key)

    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Generating audio sidecars")

    service = MediaProcessingService()
    result = service.generate_peaks(bucket_name, s3_key)

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

    if not result.get("success"):
        logger.error(
            "Audio sidecar generation failed for %s/%s: %s",
            bucket_name,
            s3_key,
            result.get("error"),
        )

    return result
