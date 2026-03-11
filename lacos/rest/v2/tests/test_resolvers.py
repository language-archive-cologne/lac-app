import pytest
from django.http import Http404

from lacos.rest.v2.resolvers import resolve_identifier
from lacos.blam.models.collection.collection_repository import Collection


@pytest.mark.django_db
class TestResolveIdentifier:
    def test_resolve_uuid(self, collection):
        result = resolve_identifier(Collection, str(collection.id))
        assert result == collection

    def test_resolve_handle(self, collection):
        result = resolve_identifier(Collection, "hdl:11341/0000-0000-0000-TEST")
        assert result == collection

    def test_resolve_handle_url_encoded(self, collection):
        result = resolve_identifier(Collection, "hdl%3A11341%2F0000-0000-0000-TEST")
        assert result == collection

    def test_not_found_raises_404(self):
        with pytest.raises(Http404):
            resolve_identifier(Collection, "nonexistent")
