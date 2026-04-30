"""S3 and storage utility functions."""

import logging
import os
import unicodedata
import xml.dom.minidom
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Optional, Tuple
from urllib.parse import quote

from botocore.exceptions import ClientError

from lacos.blam.models.bundle.bundle_structural_info import BundleAdditionalMetadataFile
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
)
from lacos.common.services.safe_html import render_safe_markdown
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
    """Return the first viable (bucket, key) pair for a resource."""
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
            logger.warning(
                "Could not verify s3://%s/%s via head_object; trusting candidate",
                bucket,
                key,
                exc_info=True,
            )
            return bucket, key
        except Exception:
            logger.warning(
                "Unexpected error verifying s3://%s/%s; trusting candidate",
                bucket,
                key,
                exc_info=True,
            )
            return bucket, key

    return None, None


def resolve_mapped_object(
    resource_service,
    location,
) -> tuple[str | None, str | None]:
    """Return mapped bucket/key only when the mapped object is still reachable."""
    bucket = getattr(location, "s3_bucket", None)
    key = getattr(location, "s3_key", None)
    if not bucket or not key:
        return None, None

    return resolve_existing_object(resource_service, [(bucket, key)])


def _strip_whitespace_nodes(node):
    """Remove whitespace-only text nodes to avoid double indentation."""
    remove = []
    for child in node.childNodes:
        if child.nodeType == child.TEXT_NODE and not child.data.strip():
            remove.append(child)
        elif child.hasChildNodes():
            _strip_whitespace_nodes(child)
    for child in remove:
        node.removeChild(child)


def load_xml_preview(
    resource_service,
    bucket_name: str,
    object_key: str,
    *,
    max_preview_bytes: int = 2 * 1024 * 1024,
) -> Optional[str]:
    """Load and pretty-format XML content for preview modals."""
    if not bucket_name or not object_key:
        return None

    try:
        response = resource_service.s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content_length = response.get("ContentLength")
        if content_length is not None and content_length > max_preview_bytes:
            return None

        raw = response["Body"].read(max_preview_bytes + 1)
        if len(raw) > max_preview_bytes:
            return None

        text = raw.decode("utf-8", errors="replace")
        doc = xml.dom.minidom.parseString(text)
        _strip_whitespace_nodes(doc)
        pretty = doc.toprettyxml(indent="  ")
        lines = pretty.split("\n")
        if lines and lines[0].startswith("<?xml"):
            lines = lines[1:]
        return "\n".join(line for line in lines if line.strip())
    except Exception:
        logger.debug(
            "Could not build XML preview for s3://%s/%s",
            bucket_name,
            object_key,
            exc_info=True,
        )
        return None


def load_markdown_preview(
    resource_service,
    bucket_name: str,
    object_key: str,
    *,
    max_preview_bytes: int = 2 * 1024 * 1024,
) -> Optional[str]:
    """Load Markdown content from S3 and convert to HTML for preview modals."""
    if not bucket_name or not object_key:
        return None

    try:
        response = resource_service.s3_client.get_object(Bucket=bucket_name, Key=object_key)
        content_length = response.get("ContentLength")
        if content_length is not None and content_length > max_preview_bytes:
            return None

        raw = response["Body"].read(max_preview_bytes + 1)
        if len(raw) > max_preview_bytes:
            return None

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        text = unicodedata.normalize("NFC", text)
        return render_safe_markdown(text)
    except Exception:
        logger.exception(
            "Could not build Markdown preview for s3://%s/%s",
            bucket_name,
            object_key,
        )
        return None


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
    stale_mapped_location: tuple[str | None, str | None] | None = None
    location = resource_service.resolve_pid_to_s3(getattr(resource, "file_pid", None))
    if (
        location
        and getattr(location, "s3_bucket", None)
        and getattr(location, "s3_key", None)
    ):
        bucket_name, object_key = resolve_mapped_object(resource_service, location)
        if not bucket_name or not object_key:
            stale_mapped_location = (location.s3_bucket, location.s3_key)
            logger.info(
                "Ignoring stale mapped S3 location for resource %s: s3://%s/%s",
                getattr(resource, "id", "unknown"),
                location.s3_bucket,
                location.s3_key,
            )
        else:
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

    fallback_bucket = (
        getattr(bundle, "import_bucket", None)
        or (
            getattr(collection_for_path, "import_bucket", None)
            if collection_for_path
            else None
        )
    ) or resource_service.production_bucket

    candidate_locations: list[tuple[Optional[str], Optional[str]]] = []
    if (
        stale_mapped_location
        and stale_mapped_location[0] != resource_service.production_bucket
    ):
        candidate_locations.append(
            (resource_service.production_bucket, stale_mapped_location[1]),
        )

    def add_import_location(import_bucket: Optional[str], import_key: Optional[str]):
        if not import_bucket or not import_key:
            return
        if isinstance(resource, BundleAdditionalMetadataFile):
            base_path = resource_service._get_ocfl_additional_metadata_base_path(import_key)
            if base_path:
                candidate_locations.append((import_bucket, f"{base_path}{resource.file_name}"))
            return

        base_path = PurePosixPath(import_key).parent
        candidate_locations.append((import_bucket, str(base_path / "Resources" / resource.file_name)))

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
                (resource_service.production_bucket, derived_key),
            )

    bucket_name, object_key = resolve_existing_object(
        resource_service,
        candidate_locations,
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


def resolve_collection_metadata_to_presigned(
    resource_service,
    metadata_file,
    collection,
    *,
    response_headers: Optional[dict] = None,
):
    """Resolve a collection additional metadata file to bucket/key/url."""
    stale_mapped_location: tuple[str | None, str | None] | None = None
    location = resource_service.resolve_pid_to_s3(
        getattr(metadata_file, "file_pid", None),
    )
    if (
        location
        and getattr(location, "s3_bucket", None)
        and getattr(location, "s3_key", None)
    ):
        bucket_name, object_key = resolve_mapped_object(resource_service, location)
        if bucket_name and object_key:
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
        stale_mapped_location = (location.s3_bucket, location.s3_key)
        logger.info(
            "Ignoring stale mapped S3 location for collection metadata %s: s3://%s/%s",
            getattr(metadata_file, "id", "unknown"),
            location.s3_bucket,
            location.s3_key,
        )

    candidate_locations: list[tuple[Optional[str], Optional[str]]] = []
    import_bucket = (
        getattr(collection, "import_bucket", None)
        or resource_service.production_bucket
    )
    import_object_key = getattr(collection, "import_object_key", None)
    if (
        stale_mapped_location
        and stale_mapped_location[0] != resource_service.production_bucket
    ):
        candidate_locations.append(
            (resource_service.production_bucket, stale_mapped_location[1]),
        )

    if isinstance(metadata_file, CollectionAdditionalMetadataFile):
        base_path = resource_service._get_ocfl_additional_metadata_base_path(import_object_key)
        if base_path:
            candidate_locations.append((import_bucket, f"{base_path}{metadata_file.file_name}"))

    file_name = getattr(metadata_file, "file_name", None)
    if import_bucket and file_name and import_object_key:
        parent = os.path.dirname(import_object_key.rstrip("/"))
        candidate_locations.append((import_bucket, f"{parent}/additional_metadata/{file_name}"))

    bucket_name, object_key = resolve_existing_object(resource_service, candidate_locations)
    if not bucket_name or not object_key:
        return None

    try:
        if hasattr(resource_service, "register_s3_location"):
            resource_service.register_s3_location(
                metadata_file,
                bucket_name,
                object_key,
                pid_url=getattr(metadata_file, "file_pid", None),
                fetch_metadata=False,
            )
    except Exception as exc:
        logger.debug(
            "Could not sync resolved collection metadata S3 location for %s: %s",
            getattr(metadata_file, "id", "unknown"),
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
