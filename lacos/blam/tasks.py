from __future__ import annotations

import gzip
from io import StringIO
import logging

from django.core.management import call_command
from huey.contrib.djhuey import task

from lacos.common.services.database_backup_service import DatabaseBackupService
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.storage.media_tasks import scan_and_generate_peaks_task
from lacos.storage.services.background_task_service import BackgroundTaskService
from lacos.storage.services.bucket_service import BucketService

logger = logging.getLogger(__name__)


@task(retries=1, retry_delay=60)
def reindex_search_vectors_task(tracking_id: str) -> dict:
    """Rebuild BLAM search vectors and persist status to BackgroundTask."""
    BackgroundTaskService.mark_running(tracking_id, message="Rebuilding search vectors")
    try:
        collections_count, bundles_count = rebuild_all_search_vectors()
        payload = {
            "success": True,
            "collections_reindexed": collections_count,
            "bundles_reindexed": bundles_count,
        }
        BackgroundTaskService.mark_success(
            tracking_id,
            message=(
                f"Reindex completed. Updated {collections_count} collections "
                f"and {bundles_count} bundles."
            ),
            result=payload,
        )
        return payload
    except Exception as exc:
        logger.error("Failed to rebuild search vectors: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload


@task(retries=1, retry_delay=300)
def backup_database_task(tracking_id: str) -> dict:
    """Create DB dump and upload to S3, tracked by BackgroundTask."""
    BackgroundTaskService.mark_running(tracking_id, message="Creating database backup")
    try:
        result = DatabaseBackupService().run()
        if result.get("success"):
            message = (
                "Backup uploaded to S3."
                f" File: {result.get('backup_file', 'unknown')}"
            )
            BackgroundTaskService.mark_success(
                tracking_id,
                message=message,
                result=result,
            )
        else:
            error_message = result.get("detail") or result.get("error") or "Database backup failed."
            return_code = result.get("returncode")
            stderr = result.get("stderr")
            if return_code is not None:
                error_message = f"{error_message} (returncode={return_code})"
            if stderr:
                trimmed_stderr = str(stderr).strip()
                if trimmed_stderr:
                    error_message = f"{error_message} stderr={trimmed_stderr}"
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=error_message,
                result=result,
            )
        return result
    except Exception as exc:
        logger.error("Failed to run database backup task: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload


@task(retries=0)
def reindex_collections_task(tracking_id: str, force: bool = False) -> dict:
    """Reindex all collections and their bundles from S3 XML."""
    mode = "forced" if force else "incremental"
    BackgroundTaskService.mark_running(
        tracking_id,
        message=f"Reindexing all collections from S3 XML ({mode})",
    )
    command_output = StringIO()
    try:
        command_args = ["reindex_collection", "--all", "--update-bundles"]
        if force:
            command_args.append("--force")

        call_command(*command_args, stdout=command_output)
        output = command_output.getvalue()
        collections_reindexed = output.count("Reindexed collection ")
        bundles_reindexed = output.count("Reindexed bundle ")
        collections_skipped = output.count("Skipped unchanged collection ")
        bundles_skipped = output.count("Skipped unchanged bundle ")
        collection_failures = output.count("Failed to reindex collection ")
        bundle_failures = output.count("Failed to reindex bundle ")

        payload = {
            "success": collection_failures == 0 and bundle_failures == 0,
            "collections_reindexed": collections_reindexed,
            "bundles_reindexed": bundles_reindexed,
            "collections_skipped": collections_skipped,
            "bundles_skipped": bundles_skipped,
            "collection_failures": collection_failures,
            "bundle_failures": bundle_failures,
            "force": force,
            "mode": mode,
        }
        if payload["success"]:
            BackgroundTaskService.mark_success(
                tracking_id,
                message=(
                    f"{mode.title()} collection reindex completed."
                    f" Collections: {collections_reindexed}, bundles: {bundles_reindexed}."
                    f" Skipped unchanged: {collections_skipped} collections, {bundles_skipped} bundles."
                ),
                result=payload,
            )
        else:
            error_message = (
                "Collection reindex finished with errors."
                f" Collection failures: {collection_failures}, bundle failures: {bundle_failures}."
            )
            payload["error"] = error_message
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=error_message,
                result=payload,
            )
        return payload
    except Exception as exc:
        logger.error("Failed to reindex collections task: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload


@task(retries=0)
def generate_all_peaks_task(tracking_id: str) -> dict:
    """Generate audio sidecars (peaks + spectrograms) for all collection buckets."""
    from lacos.blam.models.collection.collection_repository import Collection

    BackgroundTaskService.mark_running(
        tracking_id,
        message="Scanning collection buckets for audio files",
    )
    try:
        buckets = (
            Collection.objects
            .values_list("import_bucket", flat=True)
            .distinct()
        )
        buckets = [b for b in buckets if b]

        for bucket in buckets:
            scan_and_generate_peaks_task(bucket_name=bucket, force=True)

        payload = {
            "success": True,
            "buckets_scanned": len(buckets),
        }
        BackgroundTaskService.mark_success(
            tracking_id,
            message=f"Audio sidecar generation dispatched for {len(buckets)} bucket(s).",
            result=payload,
        )
        return payload
    except Exception as exc:
        logger.error("Failed to generate audio sidecars: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload


@task(retries=0)
def decompress_spectrograms_task(tracking_id: str, bucket_name: str | None = None) -> dict:
    """Re-upload gzip-encoded .spectrogram.bin files as raw bytes for range-request support."""
    from lacos.blam.models.collection.collection_repository import Collection

    target = bucket_name or "all collection buckets"
    BackgroundTaskService.mark_running(
        tracking_id,
        message=f"Scanning {target} for compressed spectrogram files",
    )
    try:
        if bucket_name:
            buckets = [bucket_name]
        else:
            buckets = (
                Collection.objects
                .values_list("import_bucket", flat=True)
                .distinct()
            )
            buckets = [b for b in buckets if b]

        bucket_service = BucketService()
        s3 = bucket_service.s3_client

        converted = 0
        skipped = 0
        errors = 0

        for bucket in buckets:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".spectrogram.bin"):
                        continue

                    try:
                        head = s3.head_object(Bucket=bucket, Key=key)
                    except Exception as exc:
                        logger.warning("HEAD %s/%s failed: %s", bucket, key, exc)
                        errors += 1
                        continue

                    if head.get("ContentEncoding", "") != "gzip":
                        skipped += 1
                        continue

                    try:
                        resp = s3.get_object(Bucket=bucket, Key=key)
                        compressed_body = resp["Body"].read()
                        metadata = head.get("Metadata", {})
                        raw_data = gzip.decompress(compressed_body)

                        s3.put_object(
                            Bucket=bucket,
                            Key=key,
                            Body=raw_data,
                            ContentType="application/octet-stream",
                            Metadata=metadata,
                        )
                        converted += 1
                    except Exception as exc:
                        logger.warning("Decompress %s/%s failed: %s", bucket, key, exc)
                        errors += 1

        payload = {
            "success": errors == 0,
            "converted": converted,
            "skipped": skipped,
            "errors": errors,
        }
        if errors == 0:
            BackgroundTaskService.mark_success(
                tracking_id,
                message=(
                    f"Spectrogram decompression complete."
                    f" Converted {converted}, skipped {skipped} (already raw)."
                ),
                result=payload,
            )
        else:
            BackgroundTaskService.mark_failed(
                tracking_id,
                error_message=(
                    f"Spectrogram decompression finished with {errors} error(s)."
                    f" Converted {converted}, skipped {skipped}."
                ),
                result=payload,
            )
        return payload
    except Exception as exc:
        logger.error("Failed to decompress spectrograms: %s", exc, exc_info=True)
        payload = {"success": False, "error": str(exc)}
        BackgroundTaskService.mark_failed(
            tracking_id,
            error_message=str(exc),
            result=payload,
        )
        return payload
