"""Record whether the player files of each audio object work.

The status comes from the files themselves (see ``media_derivative_checks``),
not from the ``source-etag`` and ``format-version`` metadata: that metadata
is missing on files uploaded outside the app, and a multipart ETag changes
when the same audio is uploaded again with another part size.

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
from lacos.storage.services.media_derivative_checks import check_player_files
from lacos.storage.services.media_processing_service import MediaProcessingService

logger = logging.getLogger(__name__)

NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
SOURCE_MISSING_PREFIX = "Source file not found"

DERIVATIVES = ("peaks", "spectrogram", "pitch")
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
    """Check with HEAD requests and short range reads that the player files work."""
    s3_client = media_service.bucket_service.s3_client
    source = _head(s3_client, bucket, s3_key)
    if source is None:
        return {
            "status": DerivativeStatus.SOURCE_MISSING,
            "source_etag": "",
            "problems": "",
        }

    keys = {
        "source": s3_key,
        "peaks": media_service._peaks_key(s3_key),
        "spectrogram": media_service._spectrogram_data_key(s3_key),
        "pitch": media_service._pitch_key(s3_key),
    }
    heads = {name: _head(s3_client, bucket, keys[name]) for name in DERIVATIVES}

    inspection = {
        "source_etag": (source.get("ETag") or "").strip('"'),
        "format_version": None,
        "audio_duration": None,
        "problems": "",
        "peaks_last_modified": None,
        "spectrogram_last_modified": None,
        "pitch_last_modified": None,
    }
    for name, head in heads.items():
        if head is not None:
            inspection[f"{name}_last_modified"] = head.get("LastModified")
    stored_version = ((heads["peaks"] or {}).get("Metadata") or {}).get(
        "format-version", ""
    )
    if stored_version.isdigit():
        inspection["format_version"] = int(stored_version)

    if any(heads[name] is None for name in REQUIRED_DERIVATIVES):
        inspection["status"] = DerivativeStatus.MISSING
        return inspection

    result = check_player_files(s3_client, bucket, source, keys, heads)
    inspection["audio_duration"] = result["audio_duration"]
    inspection["problems"] = "; ".join(result["problems"] + result["notes"])
    inspection["status"] = (
        DerivativeStatus.BROKEN if result["problems"] else DerivativeStatus.WORKS
    )
    return inspection


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

    # A failed generation leaves missing or broken files behind. Keep the
    # failure visible until the files work or the source is gone.
    keep_failure = row.status == DerivativeStatus.FAILED and inspection["status"] in {
        DerivativeStatus.MISSING,
        DerivativeStatus.BROKEN,
    }
    _apply_inspection(row, inspection)
    if keep_failure:
        row.status = DerivativeStatus.FAILED
    elif row.status == DerivativeStatus.WORKS:
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
