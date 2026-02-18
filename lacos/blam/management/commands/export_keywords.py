import csv
from collections import defaultdict

from django.core.management.base import BaseCommand

from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo


class Command(BaseCommand):
    help = "Export all keyword values with associated collection/bundle handles as CSV for normalization"

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            type=str,
            default=None,
            help="Output file path (default: stdout)",
        )

    def handle(self, *args, **options):
        coll_map = defaultdict(set)
        for gi in (
            CollectionGeneralInfo.objects.select_related("collection")
            .prefetch_related("keywords")
            .all()
        ):
            for kw in gi.keywords.all():
                coll_map[kw.value].add(gi.collection.identifier)

        bundle_map = defaultdict(set)
        for gi in (
            BundleGeneralInfo.objects.select_related("bundle")
            .prefetch_related("keywords")
            .all()
        ):
            for kw in gi.keywords.all():
                bundle_map[kw.value].add(gi.bundle.identifier)

        all_values = sorted(
            set(coll_map.keys()) | set(bundle_map.keys()),
            key=str.lower,
        )

        output = open(options["output"], "w", newline="") if options["output"] else self.stdout
        try:
            writer = csv.writer(output)
            writer.writerow([
                "current_value",
                "normalized_value",
                "wikimedia_label_en",
                "wikimedia_code",
                "collection_handles",
                "bundle_handles",
            ])
            for v in all_values:
                writer.writerow([
                    v,
                    "",
                    "",
                    "",
                    "|".join(sorted(coll_map.get(v, set()))),
                    "|".join(sorted(bundle_map.get(v, set()))),
                ])
        finally:
            if options["output"]:
                output.close()

        self.stderr.write(self.style.SUCCESS(f"Exported {len(all_values)} unique keyword values"))
