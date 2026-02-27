"""One-time migration: decompress gzip-encoded spectrogram files in S3.

Old spectrogram .bin files were uploaded with ContentEncoding=gzip.
This prevents S3 from serving HTTP Range requests on them.  This command
re-uploads each compressed file as raw bytes so range-based loading works.
"""

import gzip
import logging

from django.core.management.base import BaseCommand

from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Decompress gzip-encoded spectrogram .bin files in S3 for range-request support"

    def add_arguments(self, parser):
        parser.add_argument(
            "--bucket",
            required=True,
            help="S3 bucket name to scan",
        )
        parser.add_argument(
            "--prefix",
            default="",
            help="Limit scan to keys starting with this prefix",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be decompressed without modifying them",
        )

    def handle(self, *args, **options):
        bucket = options["bucket"]
        prefix = options["prefix"]
        dry_run = options["dry_run"]

        bucket_service = BucketService()
        s3 = bucket_service.s3_client

        self.stdout.write(f"Scanning {bucket}/{prefix or '(root)'} for .spectrogram.bin files...")

        paginator = s3.get_paginator("list_objects_v2")
        page_kwargs = {"Bucket": bucket}
        if prefix:
            page_kwargs["Prefix"] = prefix

        converted = 0
        skipped = 0
        errors = 0

        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".spectrogram.bin"):
                    continue

                # Check if the object has ContentEncoding: gzip.
                try:
                    head = s3.head_object(Bucket=bucket, Key=key)
                except Exception as exc:
                    self.stderr.write(f"  [ERROR] HEAD {key}: {exc}")
                    errors += 1
                    continue

                encoding = head.get("ContentEncoding", "")
                if encoding != "gzip":
                    skipped += 1
                    continue

                if dry_run:
                    size = head.get("ContentLength", 0)
                    self.stdout.write(f"  [WOULD DECOMPRESS] {key} ({size:,} bytes)")
                    converted += 1
                    continue

                try:
                    resp = s3.get_object(Bucket=bucket, Key=key)
                    compressed_body = resp["Body"].read()
                    metadata = head.get("Metadata", {})

                    # Decompress — the raw body from S3 is gzip when
                    # ContentEncoding=gzip *and* we bypass transparent
                    # decode by reading the stream directly.  However,
                    # boto3 does NOT auto-decompress, so the bytes are
                    # still gzip-compressed.
                    raw_data = gzip.decompress(compressed_body)

                    s3.put_object(
                        Bucket=bucket,
                        Key=key,
                        Body=raw_data,
                        ContentType="application/octet-stream",
                        Metadata=metadata,
                    )
                    converted += 1
                    self.stdout.write(f"  [OK] {key} ({len(compressed_body):,} -> {len(raw_data):,} bytes)")
                except Exception as exc:
                    self.stderr.write(f"  [ERROR] {key}: {exc}")
                    errors += 1

        action = "Would decompress" if dry_run else "Decompressed"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{action} {converted} files, skipped {skipped} (already uncompressed), {errors} errors"
            )
        )
