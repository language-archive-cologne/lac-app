"""Refresh every derived discovery projection under one revision policy."""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from lacos.explorer.discovery_refresh import DiscoveryRefreshCoordinator


class Command(BaseCommand):
    help = "Refresh search vectors, public index, and authenticated facet caches"

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-enabled",
            action="store_true",
            help="Skip when DISCOVERY_REFRESH_ENABLED is false",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignore the quiet debounce window",
        )

    def handle(self, *args, **options):
        if options["if_enabled"] and not settings.DISCOVERY_REFRESH_ENABLED:
            self.stdout.write("Discovery refresh is disabled; skipping")
            return

        result = DiscoveryRefreshCoordinator().refresh(force=options["force"])
        if result.deferred:
            self.stdout.write(
                self.style.WARNING(
                    "Discovery refresh deferred for "
                    f"{result.retry_after_seconds} seconds",
                ),
            )
            return
        if not result.success:
            message = "; ".join(result.errors) or "Discovery refresh failed"
            raise CommandError(message)
        self.stdout.write(
            self.style.SUCCESS(
                "Discovery projections refreshed at revision "
                f"{result.target_revision} with public index "
                f"{result.public_index_version}",
            ),
        )
