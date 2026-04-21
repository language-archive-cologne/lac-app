from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied

from lacos.storage.permissions import (
    can_manage_collection,
    is_archivist,
    resolve_collection_from_path,
)
from lacos.storage.services.collection_service import BucketListingPage


@dataclass(frozen=True)
class StorageDashboardAccess:
    can_manage_buckets: bool
    can_view_bucket_metrics: bool
    can_use_archivist_tools: bool


def get_storage_dashboard_access(user) -> StorageDashboardAccess:
    archivist = is_archivist(user)
    return StorageDashboardAccess(
        can_manage_buckets=archivist,
        can_view_bucket_metrics=archivist,
        can_use_archivist_tools=archivist,
    )


def get_storage_dashboard_workspace_buckets(user, bucket_service) -> list[str]:
    if is_archivist(user):
        return bucket_service.get_all_accessible_buckets()

    configured_buckets: list[str] = []
    for bucket_name in getattr(bucket_service, "workspace_buckets", []):
        resolved_name = _resolve_workspace_bucket_name(bucket_service, bucket_name)
        if resolved_name and resolved_name not in configured_buckets:
            configured_buckets.append(resolved_name)

    if not configured_buckets:
        for bucket_name in (bucket_service.ingest_bucket, bucket_service.production_bucket):
            if bucket_name and bucket_name not in configured_buckets:
                configured_buckets.append(bucket_name)

    accessible_buckets = set(bucket_service.get_all_accessible_buckets())
    filtered_buckets = [bucket for bucket in configured_buckets if bucket in accessible_buckets]
    return filtered_buckets or configured_buckets


def resolve_storage_dashboard_bucket(
    user,
    bucket_service,
    bucket_name: str | None,
    *,
    default_bucket: str | None = None,
) -> str:
    candidate = bucket_name or default_bucket
    resolved_bucket = _resolve_workspace_bucket_name(bucket_service, candidate)
    if not resolved_bucket:
        raise PermissionDenied("Bucket not allowed.")

    allowed_buckets = set(get_storage_dashboard_workspace_buckets(user, bucket_service))
    if resolved_bucket not in allowed_buckets:
        raise PermissionDenied("Bucket not allowed.")

    return resolved_bucket


def ensure_storage_dashboard_path_access(user, path: str | None) -> None:
    if is_archivist(user) or not path:
        return

    collection = resolve_collection_from_path(path)
    if not can_manage_collection(user, collection):
        raise PermissionDenied("Collection manager access required.")


def filter_storage_dashboard_listing(user, listing_page: BucketListingPage) -> BucketListingPage:
    if is_archivist(user):
        return listing_page

    filtered_items = []
    for item in listing_page:
        item_path = item.get("path")
        collection = resolve_collection_from_path(item_path)
        if can_manage_collection(user, collection):
            filtered_items.append(item)

    return BucketListingPage(
        items=filtered_items,
        has_more=listing_page.has_more,
        next_token=listing_page.next_token,
        bucket=listing_page.bucket,
        prefix=listing_page.prefix,
        raw_response=listing_page.raw_response,
    )


def _resolve_workspace_bucket_name(bucket_service, bucket_name: str | None) -> str | None:
    if not bucket_name:
        return None
    if bucket_name == "ingest":
        return bucket_service.ingest_bucket
    if bucket_name == "production":
        return bucket_service.production_bucket
    return bucket_name
