"""Huey tasks for media processing (waveform peaks generation)."""

import logging

from huey.contrib.djhuey import db_task

from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


@db_task(retries=2, retry_delay=120)
def generate_peaks_task(
    bucket_name: str, s3_key: str, tracking_id: str | None = None
) -> dict:
    """Generate waveform peaks for a single audio file."""
    logger.info("Generating peaks for %s/%s", bucket_name, s3_key)

    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Generating peaks")

    service = MediaProcessingService()
    result = service.generate_peaks(bucket_name, s3_key)

    if tracking_id:
        if result.get("success"):
            BackgroundTaskService.mark_success(
                tracking_id,
                message="Peaks generated",
                result={"peaks_key": result.get("peaks_key")},
            )
        else:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=result.get("error", "Unknown error"),
            )

    if not result.get("success"):
        logger.error("Peaks generation failed for %s/%s: %s", bucket_name, s3_key, result.get("error"))

    return result
