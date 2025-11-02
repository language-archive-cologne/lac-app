import pytest
from django.test.utils import override_settings

from lacos.storage.services.folder_cache_service import FolderStructureCacheService
from lacos.storage.services.collection_service import BucketListingPage


@pytest.mark.django_db
def test_folder_cache_service_round_trip():
    cache_service = FolderStructureCacheService()
    listing = BucketListingPage(
        items=[{"name": "alpha", "type": "file"}],
        has_more=False,
        next_token=None,
        bucket="demo",
        prefix="",
    )

    cache_service.set("demo", "", listing)
    cached = cache_service.get("demo", "")
    assert isinstance(cached, BucketListingPage)
    assert len(cached) == 1

    cache_service.invalidate("demo", "")
    assert cache_service.get("demo", "") is None


@override_settings(STORAGE_FOLDER_CACHE_ENABLED=False)
def test_folder_cache_service_disabled():
    cache_service = FolderStructureCacheService()
    cache_service.set("demo", "", ["alpha"])
    assert cache_service.get("demo", "") is None
