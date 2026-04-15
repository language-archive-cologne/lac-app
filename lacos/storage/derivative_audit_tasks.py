"""Huey tasks for derivative (sidecar) auditing."""

import logging

from huey.contrib.djhuey import db_task

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task

    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    HUEY_PERIODIC_AVAILABLE = False

from lacos.common.periodic_task_tracker import tracked_periodic
from lacos.storage.services.background_task_service import BackgroundTaskService

logger = logging.getLogger(__name__)


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


if HUEY_PERIODIC_AVAILABLE:

    @db_periodic_task(crontab(hour="3", minute="0"))
    @tracked_periodic(
        task_name="periodic_derivative_audit",
        description="Derivative Audit (daily)",
        schedule="0 3 * * *",
    )
    def periodic_derivative_audit() -> dict:
        """Daily audit of derivative status for lacos-production."""
        return _run_audit()

else:

    def periodic_derivative_audit() -> dict:  # pragma: no cover - fallback
        """Fallback when periodic tasks are unavailable."""
        return _run_audit()
