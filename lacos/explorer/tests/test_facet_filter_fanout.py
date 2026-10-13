"""Facet filters must not multiply result rows (issue #209)."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from lacos.blam.models import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.explorer.facet_definitions import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.facet_querysets import bundle_facet_queryset
from lacos.explorer.facets import FacetService
from lacos.explorer.models import BundleFileTypeFacet
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_facets import _collection_qs
from lacos.explorer.tests.test_facets import _create_collection
from lacos.explorer.tests.test_facets import _make_params

HTTP_OK = 200
BUNDLES_PER_COLLECTION = 3


def _collection_with_file_types(identifier: str, title: str):
    collection = _create_collection(
        identifier,
        title,
        languages=[("Kurdish", "kur"), ("Persian", "fas")],
    )
    for index in range(BUNDLES_PER_COLLECTION):
        bundle = Bundle.objects.create(identifier=f"{identifier}-b{index}")
        BundleStructuralInfo.objects.create(
            bundle=bundle,
            is_member_of_collection=collection,
        )
        for file_type in ("eaf", "wav", "pdf"):
            BundleFileTypeFacet.objects.create(
                bundle=bundle,
                collection=collection,
                file_type=file_type,
            )
    return collection


@pytest.mark.django_db
def test_collection_facet_filters_use_semi_joins_without_distinct():
    collection = _collection_with_file_types("C1", "Fan-out collection")

    result = FacetService().search(
        _make_params(file_type=["eaf", "wav"], language=["kur", "fas"]),
        _collection_qs(),
    )

    sql = str(result.queryset.query)
    assert "DISTINCT" not in sql
    assert "EXISTS" in sql
    assert list(result.queryset.values_list("pk", flat=True)) == [collection.pk]


@pytest.mark.django_db
def test_bundle_facet_filters_use_semi_joins_without_distinct():
    parent = _create_collection("P1", "Parent")
    bundle = _create_bundle(
        "B1",
        "Bundle",
        parent,
        languages=[("Kurdish", "kur"), ("Persian", "fas")],
    )
    _create_bundle("B2", "Other bundle", parent, languages=[("Arabic", "arb")])

    result = FacetService(definitions=BUNDLE_FACET_DEFINITIONS).search(
        _make_params(language=["kur", "fas"]),
        bundle_facet_queryset(),
    )

    assert "DISTINCT" not in str(result.queryset.query)
    assert list(result.queryset.values_list("pk", flat=True)) == [bundle.pk]


@pytest.mark.django_db
def test_access_level_filter_still_applies_to_annotation():
    _create_collection("C1", "No ACL row")

    result = FacetService().search(
        _make_params(access=["public"]),
        _collection_qs(),
    )

    assert list(result.queryset) == []


@pytest.mark.django_db
def test_collection_search_page_counts_bundles_without_fan_out(
    client,
    django_user_model,
):
    client.force_login(django_user_model.objects.create_user(username="fanout"))
    first = _collection_with_file_types("C1", "Fan-out collection")
    second = _collection_with_file_types("C2", "Other collection")

    with CaptureQueriesContext(connection) as captured:
        response = client.get(
            "/search/",
            {"file_type": ["eaf", "wav"], "language": ["kur"], "sort": "bundles"},
        )
        assert response.status_code == HTTP_OK

    collections = list(response.context["collections"])
    assert {c.pk for c in collections} == {first.pk, second.pk}
    assert {c.bundles_count for c in collections} == {BUNDLES_PER_COLLECTION}
    page_sql = [
        q["sql"]
        for q in captured.captured_queries
        if q["sql"].startswith('SELECT "blam_collection"."id"')
        or q["sql"].startswith('SELECT DISTINCT "blam_collection"."id"')
    ]
    assert page_sql
    for sql in page_sql:
        assert "SELECT DISTINCT" not in sql
        assert 'GROUP BY "blam_collection"."id"' not in sql
        assert 'JOIN "explorer_bundlefiletypefacet" ON' not in sql


@pytest.mark.django_db
@pytest.mark.parametrize("sort", ["name", "language", "bundles"])
def test_collection_search_sorts_return_each_collection_once(
    client,
    django_user_model,
    sort,
):
    client.force_login(django_user_model.objects.create_user(username=f"s-{sort}"))
    first = _collection_with_file_types("C1", "Alpha")
    second = _collection_with_file_types("C2", "Beta")

    response = client.get(
        "/search/",
        {"file_type": ["eaf", "wav"], "sort": sort, "order": "desc"},
    )

    assert response.status_code == HTTP_OK
    pks = [c.pk for c in response.context["collections"]]
    assert sorted(pks) == sorted([first.pk, second.pk])
