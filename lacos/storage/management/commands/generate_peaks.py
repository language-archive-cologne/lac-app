"""Management command to backfill audio sidecars (peaks, spectrogram, pitch) for existing audio files."""

import logging

from django.core.management.base import BaseCommand

from lacos.storage.media_tasks import generate_peaks_task
from lacos.storage.services.bucket_service import BucketService
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate audio sidecars (peaks + spectrogram + pitch) for audio files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="S3 bucket name to scan for audio files",
        )
        parser.add_argument(
            "--prefix",
            default="",
            help="Limit scan to keys starting with this prefix",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files without generating sidecars",
        )
        parser.add_argument(
            "--inline",
            action="store_true",
            help="Process inline instead of via task queue",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force regeneration even if sidecars are current",
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        prefix = options["prefix"]
        dry_run = options["dry_run"]
        inline = options["inline"]
        force = options["force"]

        bucket_service = BucketService()
        media_service = MediaProcessingService(bucket_service)

        self.stdout.write(f"Scanning {bucket}/{prefix or '(root)'} for audio files...")

        paginator = bucket_service.s3_client.get_paginator("list_objects_v2")
        page_kwargs = {"Bucket": bucket}
        if prefix:
            page_kwargs["Prefix"] = prefix

        audio_keys = []
        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.lower().endswith(".wav"):
                    audio_keys.append(key)

        self.stdout.write(f"Found {len(audio_keys)} audio files")

        enqueued = 0
        skipped = 0

        for key in audio_keys:
            if not force and media_service.derivatives_current(bucket, key):
                skipped += 1
                if dry_run:
                    self.stdout.write(f"  [SKIP] {key} (sidecars current)")
                continue

            if dry_run:
                self.stdout.write(f"  [WOULD GENERATE SIDECARS] {key}")
                enqueued += 1
                continue

            if inline:
                result = media_service.generate_peaks(bucket, key, force=force)
                status = "OK" if result.get("success") else f"FAIL: {result.get('error')}"
                self.stdout.write(f"  [{status}] {key}")
            else:
                generate_peaks_task(bucket, key, force=force)
                self.stdout.write(f"  [ENQUEUED] {key}")
            enqueued += 1

        action = "Would process" if dry_run else "Processed"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{action} {enqueued} files, skipped {skipped} (sidecars already current)"
            )
        )
