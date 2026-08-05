"""Warm collection and bundle facet caches."""

from django.core.management.base import BaseCommand

from lacos.explorer.services.facet_cache_warmer import warm_explorer_facet_caches


class Command(BaseCommand):
    help = "Warm collection and bundle facet caches"

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Invalidate existing facet caches before warming them",
        )

    def handle(self, *args, **options):
        results = warm_explorer_facet_caches(refresh=options["refresh"])
        for result in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Warmed {result.label} facets "
                    f"({result.cache_status}, {result.duration_ms:.1f} ms)",
                ),
            )
