"""Tests for ETag-based skip logic in reindex_service."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_repository import Collection
from lacos.ingest.services.reindex_service import (
    _check_etag_unchanged,
    _save_etag,
)


class TestCheckEtagUnchanged:
    def test_skip_when_etag_matches(self):
        """Happy path: returns skip=True when ETags match."""
        service = MagicMock()
        service.head_s3_object.return_value = {"ETag": "abc123"}

        skip, etag = _check_etag_unchanged(service, "bucket", "key.xml", "abc123")

        assert skip is True
        assert etag == "abc123"

    def test_no_skip_when_etag_differs(self):
        """Happy path: returns skip=False when ETags differ."""
        service = MagicMock()
        service.head_s3_object.return_value = {"ETag": "new-etag"}

        skip, etag = _check_etag_unchanged(service, "bucket", "key.xml", "old-etag")

        assert skip is False
        assert etag == "new-etag"

    def test_no_skip_when_no_stored_etag(self):
        """Edge case: first run, no stored ETag."""
        service = MagicMock()

        skip, etag = _check_etag_unchanged(service, "bucket", "key.xml", None)

        assert skip is False
        assert etag is None
        service.head_s3_object.assert_not_called()

    def test_no_skip_when_head_fails(self):
        """Error path: HEAD request fails, proceed with reindex."""
        service = MagicMock()
        service.head_s3_object.side_effect = Exception("network error")

        skip, etag = _check_etag_unchanged(service, "bucket", "key.xml", "old-etag")

        assert skip is False
        assert etag is None

    def test_no_skip_when_object_not_found(self):
        """Edge case: object deleted from S3."""
        service = MagicMock()
        service.head_s3_object.return_value = None

        skip, etag = _check_etag_unchanged(service, "bucket", "key.xml", "old-etag")

        assert skip is False
        assert etag is None


@pytest.mark.django_db
class TestSaveEtag:
    def test_saves_etag_on_collection(self):
        """Happy path: stores ETag on collection."""
        collection = Collection.objects.create(identifier=f"test-{uuid4()}")
        _save_etag(collection, "new-etag-123")

        collection.refresh_from_db()
        assert collection.import_etag == "new-etag-123"

    def test_saves_etag_on_bundle(self):
        """Happy path: stores ETag on bundle."""
        bundle = Bundle.objects.create(identifier=f"test-{uuid4()}")
        _save_etag(bundle, "bundle-etag-456")

        bundle.refresh_from_db()
        assert bundle.import_etag == "bundle-etag-456"

    def test_skips_save_when_etag_is_none(self):
        """Edge case: does not save when ETag is None."""
        collection = Collection.objects.create(identifier=f"test-{uuid4()}")
        _save_etag(collection, None)

        collection.refresh_from_db()
        assert collection.import_etag is None

    def test_skips_save_when_etag_unchanged(self):
        """Edge case: no DB write when ETag matches."""
        collection = Collection.objects.create(
            identifier=f"test-{uuid4()}", import_etag="same-etag"
        )
        with patch.object(Collection, "save") as mock_save:
            _save_etag(collection, "same-etag")
            mock_save.assert_not_called()
