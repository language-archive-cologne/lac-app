"""Tests for orphan bundle cleanup service."""

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection
from lacos.ingest.services.orphan_cleanup import (
    delete_orphaned_bundles,
    extract_bundle_folders_from_keys,
    find_orphaned_bundles,
)


# --- Unit tests for extract_bundle_folders_from_keys ---


def test_extract_folders_from_ocfl_keys():
    keys = [
        "wooi_archive/midwife/v1/metadata/midwife.xml",
        "wooi_archive/bird_story/v1/metadata/bird_story.xml",
    ]
    assert extract_bundle_folders_from_keys(keys) == {"midwife", "bird_story"}


def test_extract_folders_from_legacy_keys():
    keys = ["col-a/bundle-1/v1/content/bundle-1.xml"]
    assert extract_bundle_folders_from_keys(keys) == {"bundle-1"}


def test_extract_folders_empty_and_short_keys():
    keys = ["", "single_segment", "col/bundle/v1/content/b.xml"]
    assert extract_bundle_folders_from_keys(keys) == {"bundle"}


def test_extract_folders_deduplicates():
    keys = [
        "col/same_bundle/v1/content/a.xml",
        "col/same_bundle/v2/content/b.xml",
    ]
    assert extract_bundle_folders_from_keys(keys) == {"same_bundle"}


# --- Integration tests for find_orphaned_bundles ---


@pytest.mark.django_db
def test_find_orphaned_bundles_identifies_missing_xml():
    """Regression test for issue #95: bundle removed from XML still in DB."""
    collection = Collection.objects.create(identifier="wooi_archive_cologne")

    bundle_kept = Bundle.objects.create(
        identifier="bird_story",
        import_object_key="wooi_archive/bird_story/v1/content/bird_story.xml",
    )
    bundle_orphan = Bundle.objects.create(
        identifier="midwife",
        import_object_key="wooi_archive/midwife/v1/content/midwife.xml",
    )

    BundleStructuralInfo.objects.create(
        bundle=bundle_kept, is_member_of_collection=collection,
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle_orphan, is_member_of_collection=collection,
    )

    # S3 only has bird_story — midwife was removed from the XML
    s3_keys = ["wooi_archive/bird_story/v1/content/bird_story.xml"]

    orphans = find_orphaned_bundles(collection.id, s3_keys)

    assert len(orphans) == 1
    assert orphans[0].id == bundle_orphan.id


@pytest.mark.django_db
def test_find_orphaned_bundles_no_orphans():
    collection = Collection.objects.create(identifier="test-no-orphans")

    bundle = Bundle.objects.create(
        identifier="existing",
        import_object_key="test/existing/v1/content/existing.xml",
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection,
    )

    s3_keys = ["test/existing/v1/content/existing.xml"]
    orphans = find_orphaned_bundles(collection.id, s3_keys)

    assert orphans == []


@pytest.mark.django_db
def test_find_orphaned_bundles_missing_import_key_is_orphan():
    """A bundle with no import_object_key is treated as an orphan."""
    collection = Collection.objects.create(identifier="test-no-key")

    bundle = Bundle.objects.create(identifier="no-key-bundle")
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection,
    )

    orphans = find_orphaned_bundles(collection.id, ["test/other/v1/content/o.xml"])
    assert len(orphans) == 1


# --- Integration tests for delete_orphaned_bundles ---


@pytest.mark.django_db
def test_delete_orphaned_bundles_removes_orphan():
    """Regression test for issue #95: reindex should delete bundles removed from XML."""
    collection = Collection.objects.create(identifier="wooi-delete-test")

    bundle_kept = Bundle.objects.create(
        identifier="kept",
        import_object_key="wooi/kept/v1/content/kept.xml",
    )
    bundle_orphan = Bundle.objects.create(
        identifier="orphan",
        import_object_key="wooi/orphan/v1/content/orphan.xml",
    )

    BundleStructuralInfo.objects.create(
        bundle=bundle_kept, is_member_of_collection=collection,
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle_orphan, is_member_of_collection=collection,
    )

    s3_keys = ["wooi/kept/v1/content/kept.xml"]
    deleted = delete_orphaned_bundles(collection.id, s3_keys)

    assert bundle_orphan.id in deleted
    assert not Bundle.objects.filter(id=bundle_orphan.id).exists()
    assert Bundle.objects.filter(id=bundle_kept.id).exists()


@pytest.mark.django_db
def test_delete_orphaned_bundles_all_removed():
    """When S3 has no bundle keys, all DB bundles are orphans."""
    collection = Collection.objects.create(identifier="test-all-gone")

    b1 = Bundle.objects.create(
        identifier="b1", import_object_key="col/b1/v1/content/b1.xml",
    )
    b2 = Bundle.objects.create(
        identifier="b2", import_object_key="col/b2/v1/content/b2.xml",
    )

    BundleStructuralInfo.objects.create(
        bundle=b1, is_member_of_collection=collection,
    )
    BundleStructuralInfo.objects.create(
        bundle=b2, is_member_of_collection=collection,
    )

    deleted = delete_orphaned_bundles(collection.id, s3_bundle_keys=[])

    assert len(deleted) == 2
    assert not Bundle.objects.filter(id__in=[b1.id, b2.id]).exists()


@pytest.mark.django_db
def test_delete_orphaned_bundles_returns_empty_when_none():
    collection = Collection.objects.create(identifier="test-no-delete")
    bundle = Bundle.objects.create(
        identifier="safe", import_object_key="col/safe/v1/content/safe.xml",
    )
    BundleStructuralInfo.objects.create(
        bundle=bundle, is_member_of_collection=collection,
    )

    deleted = delete_orphaned_bundles(
        collection.id, ["col/safe/v1/content/safe.xml"],
    )

    assert deleted == []
    assert Bundle.objects.filter(id=bundle.id).exists()


@pytest.mark.django_db
def test_delete_orphaned_bundles_only_deletes_target_collection_links():
    collection_a = Collection.objects.create(identifier="test-target-a")
    collection_b = Collection.objects.create(identifier="test-target-b")

    orphan = Bundle.objects.create(
        identifier="orphan-a",
        import_object_key="col/orphan-a/v1/content/orphan-a.xml",
    )
    kept_other_collection = Bundle.objects.create(
        identifier="kept-b",
        import_object_key="col/kept-b/v1/content/kept-b.xml",
    )

    orphan_struct = BundleStructuralInfo.objects.create(
        bundle=orphan,
        is_member_of_collection=collection_a,
    )
    BundleStructuralInfo.objects.create(
        bundle=kept_other_collection,
        is_member_of_collection=collection_b,
    )

    deleted = delete_orphaned_bundles(collection_a.id, s3_bundle_keys=[])

    assert orphan.id in deleted
    assert not Bundle.objects.filter(id=orphan.id).exists()
    assert not BundleStructuralInfo.objects.filter(id=orphan_struct.id).exists()
    assert Bundle.objects.filter(id=kept_other_collection.id).exists()
