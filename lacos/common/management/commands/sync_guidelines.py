from django.core.management.base import BaseCommand

from lacos.common.tasks import sync_guidelines


class Command(BaseCommand):
    help = "Sync guidelines from lac-guidelines repository"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Run synchronously instead of enqueueing as Huey task",
        )

    def handle(self, *args, **options):
        if options["sync"]:
            self.stdout.write("Running sync_guidelines synchronously...")
            result = sync_guidelines.call_local()
        else:
            self.stdout.write("Enqueueing sync_guidelines task...")
            sync_guidelines()
            result = {"enqueued": True}

        if result.get("success"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Guidelines synced from tag {result.get('tag')}: "
                    f"{len(result.get('rendered', []))} files rendered"
                )
            )
            if result.get("errors"):
                for err in result["errors"]:
                    self.stdout.write(
                        self.style.WARNING(f"  Error: {err['file']} - {err['error']}")
                    )
        elif result.get("enqueued"):
            self.stdout.write(self.style.SUCCESS("Task enqueued successfully"))
        else:
            self.stdout.write(
                self.style.ERROR(f"Sync failed: {result.get('error', 'Unknown error')}")
            )
