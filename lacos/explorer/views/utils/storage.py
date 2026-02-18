"""S3 and storage utility functions."""

import logging
from pathlib import PurePosixPath
from typing import Optional, Sequence, Tuple
from urllib.parse import quote

from botocore.exceptions import ClientError

from lacos.storage.services.file_discovery_service import FileDiscoveryService


logger = logging.getLogger(__name__)


def build_content_disposition(file_name: Optional[str]) -> str:
    """Build a Content-Disposition header value for file downloads."""
    if not file_name:
        return "attachment"

    try:
        ascii_filename = file_name.encode("ascii", "ignore").decode("ascii")
    except Exception:
        ascii_filename = "download"

    ascii_filename = ascii_filename or "download"
    disposition = f'attachment; filename="{ascii_filename}"'

    if ascii_filename != file_name:
        disposition += f"; filename*=UTF-8''{quote(file_name)}"

    return disposition


def resolve_existing_object(
    resource_service,
    object_locations: Sequence[Tuple[Optional[str], Optional[str]]],
) -> Tuple[Optional[str], Optional[str]]:
    """Return the first (bucket, key) pair that exists in storage."""
    seen: set[Tuple[str, str]] = set()

    for bucket, key in object_locations:
        if not bucket or not key:
            continue

        identifier = (bucket, key)
        if identifier in seen:
            continue
        seen.add(identifier)

        try:
            resource_service.s3_client.head_object(Bucket=bucket, Key=key)
            return bucket, key
        except ClientError as error:
            error_code = error.response.get('Error', {}).get('Code')
            if error_code in {'404', 'NoSuchKey', 'NotFound'}:
                continue
            raise

    return None, None


def resolve_resource_to_presigned(
    resource_service,
    resource,
    bundle,
    collection_for_path,
    *,
    response_headers: Optional[dict] = None,
):
    """Resolve a resource to its storage location and presigned URL.

    Returns dict with 'bucket', 'key', and 'url' or None if not found.
    """
    fallback_bucket = (
        getattr(bundle, "import_bucket", None)
        or (
            getattr(collection_for_path, "import_bucket", None)
            if collection_for_path
            else None
        )
    ) or resource_service.production_bucket

    candidate_locations: list[tuple[Optional[str], Optional[str]]] = []

    location = resource_service.resolve_pid_to_s3(getattr(resource, "file_pid", None))
    if location:
        candidate_locations.append((location.s3_bucket, location.s3_key))
        candidate_locations.append((fallback_bucket, location.s3_key))

    def add_import_location(import_bucket: Optional[str], import_key: Optional[str]):
        if not import_bucket or not import_key:
            return
        base_path = PurePosixPath(import_key).parent
        candidate_locations.append(
            (import_bucket, str(base_path / "Resources" / resource.file_name))
        )

    add_import_location(
        getattr(bundle, "import_bucket", None),
        getattr(bundle, "import_object_key", None),
    )
    if collection_for_path:
        add_import_location(
            getattr(collection_for_path, "import_bucket", None),
            getattr(collection_for_path, "import_object_key", None),
        )

    discovery_service = FileDiscoveryService()
    derived_key = None
    if collection_for_path:
        try:
            derived_key = discovery_service.form_resource_path(
                collection_for_path.id,
                bundle.id,
                resource.file_name,
            )
        except Exception:
            derived_key = None

    if derived_key:
        candidate_locations.append((fallback_bucket, derived_key))
        if fallback_bucket != resource_service.production_bucket:
            candidate_locations.append(
                (resource_service.production_bucket, derived_key)
            )

    bucket_name, object_key = resolve_existing_object(
        resource_service, candidate_locations
    )

    if not bucket_name or not object_key:
        return None

    # Keep S3ResourceLocation aligned with the actually reachable object path so
    # protected download authorization can match bucket/key reliably.
    try:
        if hasattr(resource_service, "register_s3_location"):
            resource_service.register_s3_location(
                resource,
                bucket_name,
                object_key,
                pid_url=getattr(resource, "file_pid", None),
                fetch_metadata=False,
            )
    except Exception as exc:
        logger.debug(
            "Could not sync resolved S3 location for %s (%s): %s",
            getattr(resource, "id", "unknown"),
            getattr(resource, "file_name", "unknown"),
            exc,
        )

    presigned_url = resource_service.generate_presigned_url(
        bucket_name,
        object_key,
        response_headers=response_headers,
    )

    return {
        "bucket": bucket_name,
        "key": object_key,
        "url": presigned_url,
    }
