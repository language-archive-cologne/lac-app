import logging
from typing import Optional, Tuple
from uuid import UUID

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.storage.services.file_discovery_service import FileDiscoveryService

logger = logging.getLogger(__name__)


def reindex_collection_xml(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
) -> Optional[UUID]:
    """Reindex a collection XML stored in S3."""
    service = discovery_service or FileDiscoveryService()
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

    return collection.id


def reindex_bundle_xml(
    bucket: str,
    s3_key: str,
    update_existing: bool = True,
    discovery_service: Optional[FileDiscoveryService] = None,
) -> Optional[Tuple[UUID, UUID]]:
    """Reindex a bundle XML stored in S3."""
    service = discovery_service or FileDiscoveryService()
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

    return (bundle.id, bundle_resources_id)
