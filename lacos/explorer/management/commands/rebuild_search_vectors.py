"""
Management command to rebuild search vectors for all collections and bundles.

Usage:
    python manage.py rebuild_search_vectors
"""
from django.core.management.base import BaseCommand

from lacos.explorer.search_indexing import rebuild_all_search_vectors


class Command(BaseCommand):
    help = "Rebuild search vectors for all collections and bundles"

    def handle(self, *args, **options):
        self.stdout.write("Rebuilding search vectors...")

        collections_count, bundles_count = rebuild_all_search_vectors()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully rebuilt search vectors for {collections_count} collections "
                f"and {bundles_count} bundles."
            )
        )
