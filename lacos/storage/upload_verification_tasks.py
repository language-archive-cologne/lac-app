import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from huey.contrib.djhuey import db_task

try:
    from huey import crontab
    from huey.contrib.djhuey import db_periodic_task
    HUEY_PERIODIC_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    HUEY_PERIODIC_AVAILABLE = False

from lacos.storage.models import UploadSession
from lacos.storage.services.upload_verification_service import UploadVerificationService

logger = logging.getLogger(__name__)


def _get_grace_seconds() -> int:
    return int(getattr(settings, "UPLOAD_VERIFICATION_GRACE_SECONDS", 24 * 60 * 60))


def _get_schedule_minutes() -> int:
    return int(getattr(settings, "UPLOAD_VERIFICATION_SCHEDULE_MINUTES", 15))


@db_task(retries=3, retry_delay=60)
def verify_upload_session_task(session_id: str) -> dict:
    """Verify all files in a session and update audit records."""
    try:
        session = UploadSession.objects.get(id=session_id)
    except UploadSession.DoesNotExist:
        logger.warning("UploadSession %s not found for verification.", session_id)
        return {
            "success": False,
            "error": "UploadSession not found",
            "session_id": session_id,
        }

    service = UploadVerificationService()
    return service.verify_session(session)


def _verify_stale_sessions() -> dict:
    grace_seconds = _get_grace_seconds()
    cutoff = timezone.now() - timedelta(seconds=grace_seconds)
    sessions = UploadSession.objects.filter(
        status__in=["initialized", "in_progress"],
        created_at__lte=cutoff,
    )

    if not sessions.exists():
        return {"success": True, "sessions_checked": 0}

    service = UploadVerificationService()
    checked = 0
    failures = 0

    for session in sessions:
        try:
            service.verify_session(session)
            checked += 1
        except Exception as exc:  # pragma: no cover - logging safeguard
            failures += 1
            logger.error(
                "Failed to verify UploadSession %s: %s",
                session.id,
                exc,
            )

    return {
        "success": failures == 0,
        "sessions_checked": checked,
        "sessions_failed": failures,
    }


if HUEY_PERIODIC_AVAILABLE:
    @db_periodic_task(crontab(minute=f"*/{_get_schedule_minutes()}"))
    def verify_pending_upload_sessions() -> dict:
        """Periodically verify stale upload sessions."""
        return _verify_stale_sessions()
else:
    def verify_pending_upload_sessions() -> dict:  # pragma: no cover - fallback
        """Fallback when periodic tasks are unavailable."""
        return _verify_stale_sessions()
