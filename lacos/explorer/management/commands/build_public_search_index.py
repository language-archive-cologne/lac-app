"""Build the static anonymous public search index."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from lacos.explorer.public_search.builder import build_public_search_index
from lacos.explorer.public_search.store import write_public_search_index


class Command(BaseCommand):
    help = "Build the static anonymous public search index"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            default=None,
            help="Override the configured index output path",
        )
        parser.add_argument(
            "--if-enabled",
            action="store_true",
            help="Skip generation when PUBLIC_SEARCH_INDEX_ENABLED is false",
        )

    def handle(self, *args, **options):
        if options["if_enabled"] and not settings.PUBLIC_SEARCH_INDEX_ENABLED:
            self.stdout.write("Public search index is disabled; skipping")
            return
        target = options["output"] or Path(settings.PUBLIC_SEARCH_INDEX_PATH)
        index = build_public_search_index()
        version = write_public_search_index(target, index)
        self.stdout.write(
            self.style.SUCCESS(
                f"Built public search index {version} at {target}",
            ),
        )
