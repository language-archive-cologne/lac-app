import pytest
from django.urls import reverse

from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_repository import Collection


@pytest.mark.django_db
def test_collection_detail_htmx_bundle_per_page_50_returns_table_partial(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-page-size")
    for index in range(55):
        bundle = Bundle.objects.create(identifier=f"bundle-page-size-{index:02d}")
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.identifier},
        ),
        {"bundle_per_page": "50"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="collection-bundles-table",
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<!DOCTYPE html>" not in page
    assert page.count("data-bundle-row") == 50
    assert "1–50" in page
    assert "55 bundles" in page
    assert '<option value="50" selected' in page


@pytest.mark.django_db
def test_collection_detail_bundle_per_page_select_triggers_on_change(client):
    collection = Collection.objects.create(identifier="hdl:test/bundle-page-control")
    for index in range(11):
        bundle = Bundle.objects.create(identifier=f"bundle-page-control-{index:02d}")
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )

    response = client.get(
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.identifier},
        ),
    )

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'name="bundle_per_page"' in page
    assert 'hx-trigger="change"' in page
