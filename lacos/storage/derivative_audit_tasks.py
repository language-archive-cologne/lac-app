"""Huey tasks for derivative (sidecar) auditing."""

import logging

from huey.contrib.djhuey import db_task
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)

PERIODIC_DERIVATIVE_AUDIT_DISABLED_REASON = (
    "Automatic scheduling disabled while S3 throttling is being validated."
)


def _run_audit(bucket_name: str | None = None, prefix: str = "") -> dict:
    from lacos.storage.services.derivative_audit_service import DerivativeAuditService

    service = DerivativeAuditService()
    return service.audit_bucket(bucket_name=bucket_name, prefix=prefix)


@db_task(retries=1, retry_delay=60)
def audit_derivatives_task(
    bucket_name: str | None = None,
    prefix: str = "",
    tracking_id: str | None = None,
) -> dict:
    """On-demand derivative audit for a specific bucket/prefix."""
    if tracking_id:
        BackgroundTaskService.mark_running(tracking_id, message="Running derivative audit")

    try:
        result = _run_audit(bucket_name=bucket_name, prefix=prefix)
    except Exception as exc:
        msg = f"Derivative audit failed: {exc}"
        logger.error(msg)
        if tracking_id:
            BackgroundTaskService.mark_failed(tracking_id, error_message=msg)
        return {"success": False, "error": msg}

    if tracking_id:
        if result.get("success"):
            BackgroundTaskService.mark_success(
                tracking_id,
                message=f"Audited {result['total_wav_files']} WAV files",
                result=result,
            )
        else:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=f"Derivative audit completed with {result['errors']} errors",
                result=result,
            )
    return result


def periodic_derivative_audit() -> dict:
    """Compatibility stub kept importable while periodic scheduling is disabled."""
    logger.info("Skipping periodic derivative audit: %s", PERIODIC_DERIVATIVE_AUDIT_DISABLED_REASON)
    return {
        "success": False,
        "skipped": "periodic_derivative_audit_disabled",
        "reason": PERIODIC_DERIVATIVE_AUDIT_DISABLED_REASON,
    }
