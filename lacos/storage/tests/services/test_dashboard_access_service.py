from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied

from lacos.blam.models.collection.collection_repository import Collection
from lacos.storage.services.collection_service import BucketListingPage
from lacos.users.models import CollectionManagerAssignment
from lacos.users.tests.factories import UserFactory


def _ensure_group(name: str) -> Group:
    return Group.objects.get_or_create(name=name)[0]


@pytest.mark.django_db
def test_collection_manager_workspace_buckets_resolve_aliases():
    from lacos.storage.services.dashboard_access_service import get_storage_dashboard_workspace_buckets

    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))

    bucket_service = SimpleNamespace(
        workspace_buckets=["ingest", "production", "custom-bucket"],
        ingest_bucket="ingest-bucket",
        production_bucket="production-bucket",
        get_all_accessible_buckets=lambda: [
            "custom-bucket",
            "ingest-bucket",
            "production-bucket",
            "private-bucket",
        ],
    )

    assert get_storage_dashboard_workspace_buckets(user, bucket_service) == [
        "ingest-bucket",
        "production-bucket",
        "custom-bucket",
    ]


@pytest.mark.django_db
def test_resolve_storage_dashboard_bucket_rejects_unconfigured_bucket():
    from lacos.storage.services.dashboard_access_service import resolve_storage_dashboard_bucket

    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))

    bucket_service = SimpleNamespace(
        workspace_buckets=["ingest", "production"],
        ingest_bucket="ingest-bucket",
        production_bucket="production-bucket",
        get_all_accessible_buckets=lambda: [
            "ingest-bucket",
            "production-bucket",
            "private-bucket",
        ],
    )

    with pytest.raises(PermissionDenied):
        resolve_storage_dashboard_bucket(user, bucket_service, "private-bucket")


@pytest.mark.django_db
def test_filter_storage_dashboard_listing_keeps_assigned_collections_only():
    from lacos.storage.services.dashboard_access_service import filter_storage_dashboard_listing

    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    allowed = Collection.objects.create(identifier="collection-a")
    blocked = Collection.objects.create(identifier="collection-b")
    CollectionManagerAssignment.objects.create(user=user, collection=allowed)

    listing = BucketListingPage(
        items=[
            {"type": "folder", "name": "collection-a", "path": "collection-a/"},
            {"type": "folder", "name": "collection-b", "path": "collection-b/"},
        ],
        has_more=False,
        next_token=None,
        bucket="ingest-bucket",
        prefix="",
    )

    filtered = filter_storage_dashboard_listing(user, listing)

    assert [item["path"] for item in filtered.items] == ["collection-a/"]
    assert filtered.bucket == "ingest-bucket"
    assert filtered.prefix == ""
    assert blocked.identifier == "collection-b"


@pytest.mark.django_db
def test_ensure_storage_dashboard_path_access_denies_unassigned_collection():
    from lacos.storage.services.dashboard_access_service import ensure_storage_dashboard_path_access

    user = UserFactory()
    user.groups.add(_ensure_group("collection_manager"))
    allowed = Collection.objects.create(identifier="collection-a")
    blocked = Collection.objects.create(identifier="collection-b")
    CollectionManagerAssignment.objects.create(user=user, collection=allowed)

    with pytest.raises(PermissionDenied):
        ensure_storage_dashboard_path_access(user, "collection-b/subfolder/")

    ensure_storage_dashboard_path_access(user, "collection-a/subfolder/")
    assert blocked.identifier == "collection-b"
