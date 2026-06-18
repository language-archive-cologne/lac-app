import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import UUID

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.storage.services.file_discovery_service import FileDiscoveryService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionReindexResult:
    collection_id: UUID
    skipped: bool


@dataclass(frozen=True)
class BundleReindexResult:
    bundle_id: UUID
    bundle_resources_id: Optional[UUID]
    skipped: bool


def _check_etag_unchanged(
    service: FileDiscoveryService,
    bucket: str,
    s3_key: str,
    stored_etag: Optional[str],
) -> Tuple[bool, Optional[str]]:
    """Check if S3 object ETag matches stored value.

    Returns:
        (skip, current_etag): skip=True if unchanged, current_etag for storage.
    """
    if not stored_etag:
        return False, None
    try:
        meta = service.head_s3_object(bucket, s3_key)
    except Exception:
        return False, None
    if meta is None:
        return False, None
    current_etag = meta.get("ETag")
    if current_etag and current_etag == stored_etag:
        return True, current_etag
    return False, current_etag


def _save_etag(obj, etag: Optional[str]) -> None:
    """Store ETag on a Collection or Bundle if it changed."""
    if etag and getattr(obj, "import_etag", None) != etag:
        obj.import_etag = etag
        obj.save(update_fields=["import_etag"])


def reindex_collection_xml(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
    force: bool = False,
) -> Optional[UUID]:
    """Reindex a collection XML stored in S3.

    Skips reindex if the S3 ETag matches the stored value unless force=True.
    """
    result = reindex_collection_xml_status(
        bucket=bucket,
        s3_key=s3_key,
        update_existing=update_existing,
        discovery_service=discovery_service,
        force=force,
    )
    return result.collection_id if result else None


def reindex_collection_xml_status(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
    force: bool = False,
) -> Optional[CollectionReindexResult]:
    """Reindex collection XML and report whether it was skipped by ETag."""
    from lacos.blam.models.collection.collection_repository import Collection

    service = discovery_service or FileDiscoveryService()

    # ETag skip check — find stored etag from existing collection
    existing = Collection.objects.filter(import_object_key=s3_key).first()
    stored_etag = getattr(existing, "import_etag", None) if existing else None
    current_etag = None
    if not force:
        skip, current_etag = _check_etag_unchanged(service, bucket, s3_key, stored_etag)
        if skip:
            logger.info("Collection unchanged (ETag match), skipping %s", s3_key)
            return CollectionReindexResult(collection_id=existing.id, skipped=True)

    try:
        xml_content_bytes = service.read_s3_object(bucket, s3_key)
    except Exception as exc:
        logger.error(
            "Collection reindex failed: error reading %s/%s: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    if not xml_content_bytes:
        logger.error("Collection reindex failed: XML not found at %s/%s", bucket, s3_key)
        return None

    try:
        xml_content = xml_content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        logger.error(
            "Collection reindex failed: XML at %s/%s is not UTF-8: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    try:
        collection = CollectionImporter.import_from_xml(
            xml_content,
            update_existing=update_existing,
        )
    except Exception as exc:
        logger.warning(
            "Collection reindex skipped for %s/%s: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    fields_to_update = []
    if getattr(collection, "import_bucket", None) != bucket:
        collection.import_bucket = bucket
        fields_to_update.append("import_bucket")
    if getattr(collection, "import_object_key", None) != s3_key:
        collection.import_object_key = s3_key
        fields_to_update.append("import_object_key")
    if fields_to_update:
        collection.save(update_fields=fields_to_update)

    # Store ETag after successful reindex
    if not current_etag:
        meta = service.head_s3_object(bucket, s3_key)
        current_etag = meta.get("ETag") if meta else None
    _save_etag(collection, current_etag)

    return CollectionReindexResult(collection_id=collection.id, skipped=False)


def reindex_bundle_xml(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
    force: bool = False,
) -> Optional[Tuple[UUID, Optional[UUID]]]:
    """Reindex a bundle XML stored in S3.

    Skips reindex if the S3 ETag matches the stored value unless force=True.
    """
    result = reindex_bundle_xml_status(
        bucket=bucket,
        s3_key=s3_key,
        update_existing=update_existing,
        discovery_service=discovery_service,
        force=force,
    )
    if not result:
        return None
    return (result.bundle_id, result.bundle_resources_id)


def reindex_bundle_xml_status(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
    force: bool = False,
) -> Optional[BundleReindexResult]:
    """Reindex bundle XML and report whether it was skipped by ETag."""
    from lacos.blam.models.bundle.bundle_repository import Bundle

    service = discovery_service or FileDiscoveryService()

    # ETag skip check
    existing = Bundle.objects.filter(import_object_key=s3_key).first()
    stored_etag = getattr(existing, "import_etag", None) if existing else None
    current_etag = None
    if not force:
        skip, current_etag = _check_etag_unchanged(service, bucket, s3_key, stored_etag)
        if skip:
            logger.info("Bundle unchanged (ETag match), skipping %s", s3_key)
            from lacos.explorer.services.file_type_facets import (
                refresh_bundle_file_type_facets,
            )

            refresh_bundle_file_type_facets(existing)
            resources = existing.resources.first()
            return BundleReindexResult(
                bundle_id=existing.id,
                bundle_resources_id=resources.id if resources else None,
                skipped=True,
            )

    try:
        xml_content_bytes = service.read_s3_object(bucket, s3_key)
    except Exception as exc:
        logger.error(
            "Bundle reindex failed: error reading %s/%s: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    if not xml_content_bytes:
        logger.error("Bundle reindex failed: XML not found at %s/%s", bucket, s3_key)
        return None

    try:
        xml_content = xml_content_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        logger.error(
            "Bundle reindex failed: XML at %s/%s is not UTF-8: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    try:
        importer_result = BundleImporter.import_from_xml(
            xml_content,
            update_existing=update_existing,
        )
    except Exception as exc:
        logger.warning(
            "Bundle reindex skipped for %s/%s: %s",
            bucket,
            s3_key,
            exc,
        )
        return None

    if not importer_result:
        logger.error("Bundle reindex failed: importer returned no result for %s/%s", bucket, s3_key)
        return None

    bundle, bundle_resources_id = importer_result
    if not bundle or not bundle_resources_id:
        logger.error(
            "Bundle reindex failed: missing bundle or resources for %s/%s",
            bucket,
            s3_key,
        )
        return None

    fields_to_update = []
    if getattr(bundle, "import_bucket", None) != bucket:
        bundle.import_bucket = bucket
        fields_to_update.append("import_bucket")
    if getattr(bundle, "import_object_key", None) != s3_key:
        bundle.import_object_key = s3_key
        fields_to_update.append("import_object_key")
    if fields_to_update:
        bundle.save(update_fields=fields_to_update)

    # Store ETag after successful reindex
    if not current_etag:
        meta = service.head_s3_object(bucket, s3_key)
        current_etag = meta.get("ETag") if meta else None
    _save_etag(bundle, current_etag)

    return BundleReindexResult(
        bundle_id=bundle.id,
        bundle_resources_id=bundle_resources_id,
        skipped=False,
    )
