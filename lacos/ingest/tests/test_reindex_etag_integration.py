"""Integration tests for ETag-based skip logic in the full reindex flow."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import (
    BundleResources,
    BundleStructuralInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
)
from lacos.ingest.services.reindex_service import (
    reindex_bundle_xml,
    reindex_collection_xml,
)


@pytest.fixture
def discovery_service():
    svc = MagicMock()
    svc.head_s3_object.return_value = {"ETag": "etag-abc123"}
    svc.read_s3_object.return_value = b"<xml>content</xml>"
    return svc


@pytest.mark.django_db
class TestCollectionEtagSkip:
    def test_first_reindex_stores_etag(self, discovery_service):
        """First reindex: no ETag stored, full reindex runs, ETag saved."""
        collection = Collection.objects.create(
            identifier=f"test-{uuid4()}",
            import_object_key="coll/coll/v1/metadata/coll.xml",
            import_etag=None,
        )

        with patch(
            "lacos.ingest.services.reindex_service.CollectionImporter.import_from_xml",
            return_value=collection,
        ):
            result = reindex_collection_xml(
                bucket="bucket",
                s3_key="coll/coll/v1/metadata/coll.xml",
                discovery_service=discovery_service,
            )

        assert result == collection.id
        # Full reindex happened: read_s3_object was called
        discovery_service.read_s3_object.assert_called_once()
        # ETag was stored
        collection.refresh_from_db()
        assert collection.import_etag == "etag-abc123"

    def test_second_reindex_skips_when_etag_matches(self, discovery_service):
        """Second reindex: ETag matches, skip download and parsing."""
        collection = Collection.objects.create(
            identifier=f"test-{uuid4()}",
            import_object_key="coll/coll/v1/metadata/coll.xml",
            import_etag="etag-abc123",
        )

        result = reindex_collection_xml(
            bucket="bucket",
            s3_key="coll/coll/v1/metadata/coll.xml",
            discovery_service=discovery_service,
        )

        assert result == collection.id
        # Skipped: read_s3_object was NOT called
        discovery_service.read_s3_object.assert_not_called()

    def test_reindex_runs_when_etag_differs(self, discovery_service):
        """ETag changed in S3: full reindex runs."""
        discovery_service.head_s3_object.return_value = {"ETag": "new-etag-xyz"}
        collection = Collection.objects.create(
            identifier=f"test-{uuid4()}",
            import_object_key="coll/coll/v1/metadata/coll.xml",
            import_etag="old-etag-abc",
        )

        with patch(
            "lacos.ingest.services.reindex_service.CollectionImporter.import_from_xml",
            return_value=collection,
        ):
            result = reindex_collection_xml(
                bucket="bucket",
                s3_key="coll/coll/v1/metadata/coll.xml",
                discovery_service=discovery_service,
            )

        assert result == collection.id
        # Full reindex happened
        discovery_service.read_s3_object.assert_called_once()
        # New ETag stored
        collection.refresh_from_db()
        assert collection.import_etag == "new-etag-xyz"


@pytest.mark.django_db
class TestBundleEtagSkip:
    def _make_bundle_with_resources(self, collection, etag=None):
        bundle = Bundle.objects.create(
            identifier=f"test-bundle-{uuid4()}",
            import_object_key="coll/bundle/v1/metadata/bundle.xml",
            import_etag=etag,
        )
        struct_info = BundleStructuralInfo.objects.create(
            is_member_of_collection=collection,
            bundle=bundle,
        )
        resources = BundleResources.objects.create(bundle=bundle)
        return bundle, resources

    def test_first_reindex_stores_etag(self, discovery_service):
        """First bundle reindex: no ETag, full reindex, ETag saved."""
        collection = Collection.objects.create(identifier=f"coll-{uuid4()}")
        bundle, resources = self._make_bundle_with_resources(collection, etag=None)

        with patch(
            "lacos.ingest.services.reindex_service.BundleImporter.import_from_xml",
            return_value=(bundle, resources.id),
        ):
            result = reindex_bundle_xml(
                bucket="bucket",
                s3_key="coll/bundle/v1/metadata/bundle.xml",
                discovery_service=discovery_service,
            )

        assert result == (bundle.id, resources.id)
        discovery_service.read_s3_object.assert_called_once()
        bundle.refresh_from_db()
        assert bundle.import_etag == "etag-abc123"

    def test_second_reindex_skips_when_etag_matches(self, discovery_service):
        """Second bundle reindex: ETag matches, skip."""
        collection = Collection.objects.create(identifier=f"coll-{uuid4()}")
        bundle, resources = self._make_bundle_with_resources(
            collection, etag="etag-abc123"
        )

        result = reindex_bundle_xml(
            bucket="bucket",
            s3_key="coll/bundle/v1/metadata/bundle.xml",
            discovery_service=discovery_service,
        )

        assert result == (bundle.id, resources.id)
        discovery_service.read_s3_object.assert_not_called()

    def test_reindex_runs_when_etag_differs(self, discovery_service):
        """Bundle ETag changed: full reindex runs."""
        discovery_service.head_s3_object.return_value = {"ETag": "new-etag"}
        collection = Collection.objects.create(identifier=f"coll-{uuid4()}")
        bundle, resources = self._make_bundle_with_resources(
            collection, etag="old-etag"
        )

        with patch(
            "lacos.ingest.services.reindex_service.BundleImporter.import_from_xml",
            return_value=(bundle, resources.id),
        ):
            result = reindex_bundle_xml(
                bucket="bucket",
                s3_key="coll/bundle/v1/metadata/bundle.xml",
                discovery_service=discovery_service,
            )

        assert result == (bundle.id, resources.id)
        discovery_service.read_s3_object.assert_called_once()
        bundle.refresh_from_db()
        assert bundle.import_etag == "new-etag"

    def test_skip_returns_none_resources_when_no_bundle_resources(self, discovery_service):
        """ETag skip for bundle without BundleResources returns (id, None)."""
        collection = Collection.objects.create(identifier=f"coll-{uuid4()}")
        bundle = Bundle.objects.create(
            identifier=f"bundle-{uuid4()}",
            import_object_key="coll/bundle/v1/metadata/bundle.xml",
            import_etag="etag-abc123",
        )
        BundleStructuralInfo.objects.create(
            is_member_of_collection=collection, bundle=bundle
        )
        # No BundleResources created

        result = reindex_bundle_xml(
            bucket="bucket",
            s3_key="coll/bundle/v1/metadata/bundle.xml",
            discovery_service=discovery_service,
        )

        assert result == (bundle.id, None)
        discovery_service.read_s3_object.assert_not_called()
