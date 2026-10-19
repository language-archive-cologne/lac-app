"""Record audio derivative status and ELAN audio links for collections."""

import uuid

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.services.media_audit_service import MediaAuditService


class Command(BaseCommand):
    help = (
        "Record the derivative status of audio files and the audio link of ELAN "
        "files. Changes no S3 object."
    )

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument(
            "--collection",
            help="Collection id (UUID) or identifier",
        )
        target.add_argument(
            "--all",
            action="store_true",
            help="Audit all collections",
        )

    def handle(self, *args, **options):
        service = MediaAuditService()
        if options["all"]:
            service.audit_all_collections(
                on_collection=lambda c: self.stdout.write(
                    f"Auditing {c.identifier} ..."
                ),
            )
        else:
            collection = self._get_collection(options["collection"])
            self.stdout.write(f"Auditing {collection.identifier} ...")
            service.audit_collection(collection)

        self.stdout.write(self.style.SUCCESS("Audit complete"))
        for name, count in sorted(service.counts.items()):
            self.stdout.write(f"  {name}: {count}")

    @staticmethod
    def _get_collection(value: str) -> Collection:
        lookup = {"identifier": value}
        try:
            lookup = {"id": uuid.UUID(value)}
        except ValueError:
            pass
        try:
            return Collection.objects.get(**lookup)
        except Collection.DoesNotExist as exc:
            raise CommandError(f"Collection not found: {value}") from exc
