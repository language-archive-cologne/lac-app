import logging
import os
import sys

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class StorageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lacos.storage"

    def ready(self):
        """
        Optionally run an ACL sync once the app starts up.
        """
        super().ready()

        if not getattr(settings, "ACL_SYNC_ON_STARTUP", False):
            return

        if os.environ.get("DJANGO_SKIP_ACL_SYNC") == "1":
            return

        # Skip automatic sync while running tests
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return

        # Avoid running during management commands that don't require sync (e.g. migrations, tests)
        if len(sys.argv) > 1 and sys.argv[1] in {"migrate", "makemigrations", "collectstatic", "test"}:
            return

        # Avoid running twice with the autoreloader in DEBUG mode
        if settings.DEBUG and os.environ.get("RUN_MAIN") != "true":
            return

        if sys.argv and "pytest" in sys.argv[0]:
            return

        try:
            from lacos.storage.services.acl_sync_service import ACLSyncService

            service = ACLSyncService()
            results = service.sync_all()
            synced = sum(1 for result in results if result.updated and result.error is None)
            logger.info("ACL sync on startup complete - processed %s objects", synced)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("ACL sync on startup failed: %s", exc, exc_info=True)
