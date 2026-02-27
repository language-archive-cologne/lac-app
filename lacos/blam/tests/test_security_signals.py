"""
Tests for BLAM security audit signals (Collection and Bundle deletion logging).
"""
import pytest

from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo


def create_test_collection(collection_id="test_coll_security"):
    """Create a minimal test Collection."""
    return Collection.objects.create(identifier=collection_id)


def create_test_bundle(bundle_id="test_bundle_security", collection=None):
    """Create a minimal test Bundle with optional collection relationship via structural info."""
    bundle = Bundle.objects.create(identifier=bundle_id)
    if collection:
        # Create structural info linking bundle to collection
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )
    return bundle


@pytest.mark.django_db
class TestCollectionDeletionLogging:
    """Tests for Collection deletion security logging."""

    def test_collection_deletion_logs_warning(self, caplog):
        """Test that collection deletion is logged as warning."""
        collection = create_test_collection(collection_id="delete_me_collection")
        collection_pk = collection.pk

        with caplog.at_level("WARNING", logger="lacos.security"):
            collection.delete()

        assert "COLLECTION_DELETED" in caplog.text
        record = next(r for r in caplog.records if r.getMessage() == "COLLECTION_DELETED")
        assert record.pk == collection_pk

    def test_collection_deletion_logs_name(self, caplog):
        """Test that collection name is included in log."""
        collection = create_test_collection()

        with caplog.at_level("WARNING", logger="lacos.security"):
            collection.delete()

        assert "COLLECTION_DELETED" in caplog.text
        record = next(r for r in caplog.records if r.getMessage() == "COLLECTION_DELETED")
        assert hasattr(record, "collection_name")


@pytest.mark.django_db
class TestBundleDeletionLogging:
    """Tests for Bundle deletion security logging."""

    def test_bundle_deletion_logs_warning(self, caplog):
        """Test that bundle deletion is logged as warning."""
        bundle = create_test_bundle(bundle_id="delete_me_bundle")
        bundle_pk = bundle.pk

        with caplog.at_level("WARNING", logger="lacos.security"):
            bundle.delete()

        assert "BUNDLE_DELETED" in caplog.text
        record = next(r for r in caplog.records if r.getMessage() == "BUNDLE_DELETED")
        assert record.pk == bundle_pk

    def test_bundle_deletion_logs_name(self, caplog):
        """Test that bundle name is included in log."""
        bundle = create_test_bundle()

        with caplog.at_level("WARNING", logger="lacos.security"):
            bundle.delete()

        assert "BUNDLE_DELETED" in caplog.text
        record = next(r for r in caplog.records if r.getMessage() == "BUNDLE_DELETED")
        assert hasattr(record, "bundle_name")

    def test_bundle_with_collection_deletion_logs_both(self, caplog):
        """Test that deleting a bundle linked to a collection logs bundle deletion.

        Note: Due to the FK relationship direction (BundleStructuralInfo.bundle -> Bundle),
        deleting a Collection only cascades to BundleStructuralInfo, not to the Bundle itself.
        This test verifies that explicitly deleting a bundle is properly logged.
        """
        collection = create_test_collection(collection_id="parent_collection")
        bundle = create_test_bundle(bundle_id="child_bundle", collection=collection)

        with caplog.at_level("WARNING", logger="lacos.security"):
            bundle.delete()
            collection.delete()

        assert "BUNDLE_DELETED" in caplog.text
        assert "COLLECTION_DELETED" in caplog.text
