import logging
import time

from django.core.management.base import BaseCommand, CommandError

from lacos.storage.services.registry import get_base_storage_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Warm the storage service cache by prefetching workspace buckets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            dest="refresh",
            help="Force a fresh S3 listing instead of serving cached results.",
        )

    def handle(self, *args, **options):
        refresh = options.get("refresh", False)

        try:
            base_service = get_base_storage_service(skip_bucket_check=False)

            start = time.monotonic()
            buckets = base_service.get_all_accessible_buckets(
                force_refresh=refresh,
                raise_on_error=True,
            )
            duration = time.monotonic() - start

            metadata = base_service.bucket_cache_metadata
            bucket_count = len(buckets)

            logger.info(
                "storage.prefetch",
                extra={
                    "event": "storage.prefetch",
                    "bucket_count": bucket_count,
                    "duration": duration,
                    "force_refresh": refresh,
                    "cache_source": metadata.get("source"),
                },
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Prefetched {bucket_count} bucket(s) in {duration:.2f}s (source={metadata.get('source', 'unknown')})."
                )
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Storage prefetch failed: %s", exc, exc_info=True)
            raise CommandError(f"Prefetch failed: {exc}")
