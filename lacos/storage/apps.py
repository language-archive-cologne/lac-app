import logging
import os
import sys
import time

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
            from lacos.storage.services.registry import get_acl_sync_service, get_base_storage_service
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to import storage registry helpers: %s", exc, exc_info=True)
            get_acl_sync_service = get_base_storage_service = None  # type: ignore[assignment]

        if get_acl_sync_service:
            try:
                service = get_acl_sync_service()
                sync_start = time.monotonic()
                results = service.sync_all()
                sync_duration = time.monotonic() - sync_start
                synced = sum(1 for result in results if result.updated and result.error is None)
                logger.info(
                    "ACL sync on startup complete - processed %s objects in %.2fs",
                    synced,
                    sync_duration,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("ACL sync on startup failed: %s", exc, exc_info=True)

        if get_base_storage_service and getattr(settings, "STORAGE_PREFETCH_BUCKETS_ON_STARTUP", False):
            try:
                base_service = get_base_storage_service(skip_bucket_check=True)
                prefetch_start = time.monotonic()
                buckets = base_service.get_all_accessible_buckets(force_refresh=True, raise_on_error=False)
                prefetch_duration = time.monotonic() - prefetch_start
                logger.info(
                    "Prefetched %s storage bucket(s) on startup in %.2fs",
                    len(buckets),
                    prefetch_duration,
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Bucket prefetch on startup failed: %s", exc, exc_info=True)

        from lacos.storage.services.base_storage_service import BaseStorageService

        BaseStorageService.mark_startup_complete()
