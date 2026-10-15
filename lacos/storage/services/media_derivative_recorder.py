"""Record the state of audio derivatives in ``MediaDerivativeStatus``.

The generation task, the ``generate_peaks`` command, ``audit_media`` and the
nightly check all write through this module, so the rules for a status live
in one place.
"""

import logging

from botocore.exceptions import ClientError
from django.utils import timezone

from lacos.storage.models import MediaDerivativeStatus
from lacos.storage.models import S3ResourceLocation
from lacos.storage.models.media_derivatives import DerivativeStatus
from lacos.storage.services.media_processing_service import DERIVATIVE_FORMAT_VERSION
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)

NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
SOURCE_MISSING_PREFIX = "Source file not found"

# Pitch is optional: generation writes no pitch file for very short audio.
REQUIRED_DERIVATIVES = ("peaks", "spectrogram")


def _head(s3_client, bucket: str, key: str) -> dict | None:
    """Return the HEAD response of an object, or None when it does not exist."""
    try:
        return s3_client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in NOT_FOUND_CODES:
            return None
        raise


def inspect_derivatives(
    media_service: MediaProcessingService, bucket: str, s3_key: str
) -> dict:
    """Read the source and derivative objects with HEAD requests only."""
    s3_client = media_service.bucket_service.s3_client
    source = _head(s3_client, bucket, s3_key)
    if source is None:
        return {"status": DerivativeStatus.SOURCE_MISSING, "source_etag": ""}

    source_etag = (source.get("ETag") or "").strip('"')
    derivative_keys = {
        "peaks": media_service._peaks_key(s3_key),
        "spectrogram": media_service._spectrogram_data_key(s3_key),
        "pitch": media_service._pitch_key(s3_key),
    }

    states: dict[str, str] = {}
    last_modified: dict[str, object] = {}
    format_version = None
    for name, key in derivative_keys.items():
        response = _head(s3_client, bucket, key)
        if response is None:
            states[name] = DerivativeStatus.MISSING
            last_modified[name] = None
            continue

        metadata = response.get("Metadata", {})
        stored_version = metadata.get("format-version", "")
        if name == "peaks" and stored_version.isdigit():
            format_version = int(stored_version)
        is_current = metadata.get(
            "source-etag", ""
        ) == source_etag and stored_version == str(DERIVATIVE_FORMAT_VERSION)
        states[name] = (
            DerivativeStatus.CURRENT if is_current else DerivativeStatus.STALE
        )
        last_modified[name] = response.get("LastModified")

    if any(states[name] == DerivativeStatus.MISSING for name in REQUIRED_DERIVATIVES):
        status = DerivativeStatus.MISSING
    elif DerivativeStatus.STALE in states.values():
        status = DerivativeStatus.STALE
    else:
        status = DerivativeStatus.CURRENT

    return {
        "status": status,
        "source_etag": source_etag,
        "format_version": format_version,
        "peaks_last_modified": last_modified["peaks"],
        "spectrogram_last_modified": last_modified["spectrogram"],
        "pitch_last_modified": last_modified["pitch"],
    }


def collection_for_object(bucket: str, s3_key: str):
    """Find the collection of the BLAM resource stored at bucket/key, if any."""
    from lacos.blam.models.bundle.bundle_structural_info import BundleResources

    location = (
        S3ResourceLocation.objects.filter(s3_bucket=bucket, s3_key=s3_key)
        .select_related("content_type")
        .first()
    )
    if location is None:
        return None

    relation = {
        "mediaresource": "bundle_media_resources",
        "writtenresource": "bundle_written_resources",
        "otherresource": "bundle_other_resources",
    }.get(location.content_type.model)
    if relation is None:
        return None

    container = (
        BundleResources.objects.filter(**{f"{relation}__id": location.object_id})
        .select_related("bundle")
        .first()
    )
    if container is None:
        return None
    structural_info = container.bundle.structural_info.select_related(
        "is_member_of_collection",
    ).first()
    return structural_info.is_member_of_collection if structural_info else None


def _get_row(bucket: str, s3_key: str, collection) -> MediaDerivativeStatus:
    row, _ = MediaDerivativeStatus.objects.get_or_create(bucket=bucket, s3_key=s3_key)
    if collection is not None:
        row.collection = collection
    elif row.collection_id is None:
        row.collection = collection_for_object(bucket, s3_key)
    return row


def _apply_inspection(row: MediaDerivativeStatus, inspection: dict) -> None:
    for field, value in inspection.items():
        setattr(row, field, value)
    row.last_checked_at = timezone.now()


def record_check(
    bucket: str,
    s3_key: str,
    *,
    media_service: MediaProcessingService | None = None,
    collection=None,
) -> MediaDerivativeStatus:
    """Update the status of one audio object from S3. Generate nothing."""
    media_service = media_service or MediaProcessingService()
    inspection = inspect_derivatives(media_service, bucket, s3_key)
    row = _get_row(bucket, s3_key, collection)

    # A failed generation leaves missing or stale files behind. Keep the
    # failure visible until the files are current or the source is gone.
    keep_failure = row.status == DerivativeStatus.FAILED and inspection["status"] in {
        DerivativeStatus.MISSING,
        DerivativeStatus.STALE,
    }
    _apply_inspection(row, inspection)
    if keep_failure:
        row.status = DerivativeStatus.FAILED
    elif row.status == DerivativeStatus.CURRENT:
        row.last_error = ""
    row.save()
    return row


def record_generation(
    bucket: str,
    s3_key: str,
    result: dict,
    *,
    media_service: MediaProcessingService | None = None,
    collection=None,
) -> MediaDerivativeStatus | None:
    """Record the result of ``MediaProcessingService.generate_peaks``.

    The recorder never makes the generation fail: errors are logged.
    """
    try:
        if result.get("success"):
            return record_check(
                bucket,
                s3_key,
                media_service=media_service,
                collection=collection,
            )

        error = str(result.get("error") or "Unknown error")
        row = _get_row(bucket, s3_key, collection)
        if error.startswith(SOURCE_MISSING_PREFIX):
            row.status = DerivativeStatus.SOURCE_MISSING
        else:
            row.status = DerivativeStatus.FAILED
        row.last_error = error
        row.last_checked_at = timezone.now()
        row.save()
        return row
    except Exception:
        logger.exception("Could not record derivative status for %s/%s", bucket, s3_key)
        return None
