"""Detect and remove bundles whose XML no longer exists in S3."""

import logging
from typing import Set
from uuid import UUID

logger = logging.getLogger(__name__)


def extract_bundle_folders_from_keys(s3_keys: list[str]) -> Set[str]:
    """Extract bundle folder names from S3 object keys.

    S3 key formats:
        OCFL 1.1: ``collection/bundle_folder/v1/metadata/bundle.xml``
        Legacy:   ``collection/bundle_folder/v1/content/bundle.xml``

    The bundle folder is always the second path segment.
    """
    folders: Set[str] = set()
    for key in s3_keys:
        parts = key.split("/")
        if len(parts) >= 2:
            folders.add(parts[1])
    return folders


def find_orphaned_bundles(
    collection_id: UUID,
    s3_bundle_keys: list[str],
) -> list:
    """Return bundles linked to *collection_id* that have no matching S3 key.

    A bundle is considered orphaned when its ``import_object_key`` folder
    segment does not appear among the folders derived from *s3_bundle_keys*.
    """
    from lacos.blam.models.bundle.bundle_repository import Bundle
    from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo

    s3_folders = extract_bundle_folders_from_keys(s3_bundle_keys)

    linked_ids = BundleStructuralInfo.objects.filter(
        is_member_of_collection_id=collection_id,
    ).values_list("bundle_id", flat=True)

    orphans = []
    for bundle in Bundle.objects.filter(id__in=linked_ids):
        bundle_folder = None
        if bundle.import_object_key:
            parts = bundle.import_object_key.split("/")
            if len(parts) >= 2:
                bundle_folder = parts[1]

        if bundle_folder is None or bundle_folder not in s3_folders:
            orphans.append(bundle)

    return orphans


def delete_orphaned_bundles(
    collection_id: UUID,
    s3_bundle_keys: list[str],
) -> list[UUID]:
    """Delete bundles linked to *collection_id* that no longer exist in S3.

    Returns the IDs of deleted bundles.
    """
    orphans = find_orphaned_bundles(collection_id, s3_bundle_keys)
    deleted: list[UUID] = []

    for bundle in orphans:
        bid, ident = bundle.id, bundle.identifier
        try:
            bundle.delete()
            deleted.append(bid)
            logger.info(
                "Deleted orphaned bundle %s (%s) from collection %s",
                ident, bid, collection_id,
            )
        except Exception:
            logger.exception("Failed to delete orphaned bundle %s", bid)

    return deleted
