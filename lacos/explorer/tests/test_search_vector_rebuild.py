"""The search vector rebuild writes only changed rows (issue #209)."""

import pytest

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo
from lacos.explorer.search_indexing import rebuild_all_search_vectors
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_facets import _create_collection


@pytest.mark.django_db
def test_rebuild_skips_rows_whose_vector_did_not_change():
    collection = _create_collection("C1", "Collection")
    _create_bundle("B1", "First bundle", collection)
    _create_bundle("B2", "Second bundle", collection)

    assert rebuild_all_search_vectors() == (1, 2)
    assert rebuild_all_search_vectors() == (0, 0)


@pytest.mark.django_db
def test_rebuild_updates_only_the_changed_bundle():
    collection = _create_collection("C1", "Collection")
    changed = _create_bundle("B1", "First bundle", collection)
    _create_bundle("B2", "Second bundle", collection)
    rebuild_all_search_vectors()

    BundleGeneralInfo.objects.filter(bundle=changed).update(
        display_title="Renamed zanzibar",
    )

    assert rebuild_all_search_vectors() == (0, 1)
    assert Bundle.objects.filter(search_vector="zanzibar").get() == changed
