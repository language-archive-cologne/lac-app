"""Query-scaling regressions for authenticated faceted explorer searches."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_bundle_facets import _create_collection as _create_parent
from lacos.explorer.tests.test_facets import _create_collection

HTTP_OK = 200
COLLECTION_QUERY_BUDGET = 16
BUNDLE_QUERY_BUDGET = 21


def _capture_search(client, path: str, params: dict, *, htmx: bool) -> int:
    cache.clear()
    headers = (
        {
            "HTTP_HX_REQUEST": "true",
            "HTTP_HX_TARGET": "faceted-results",
        }
        if htmx
        else {}
    )
    with CaptureQueriesContext(connection) as captured:
        response = client.get(path, params, **headers)
        assert response.status_code == HTTP_OK
        _ = response.content
    return len(captured)


@pytest.mark.django_db
@pytest.mark.parametrize("htmx", [False, True])
def test_collection_faceted_search_queries_do_not_grow_with_page_size(
    client,
    django_user_model,
    htmx,
):
    client.force_login(
        django_user_model.objects.create_user(username=f"collection-search-{htmx}"),
    )
    _create_collection("small-collection", "Small collection", country="Small")
    for index in range(25):
        _create_collection(
            f"large-collection-{index}",
            f"Large collection {index}",
            country="Large",
        )
    ContentType.objects.get_for_model(Collection)

    small_queries = _capture_search(client, "/search/", {"country": "Small"}, htmx=htmx)
    large_queries = _capture_search(client, "/search/", {"country": "Large"}, htmx=htmx)

    assert small_queries <= COLLECTION_QUERY_BUDGET
    assert large_queries == small_queries


@pytest.mark.django_db
@pytest.mark.parametrize("htmx", [False, True])
def test_bundle_faceted_search_queries_do_not_grow_with_page_size(
    client,
    django_user_model,
    htmx,
):
    client.force_login(
        django_user_model.objects.create_user(username=f"bundle-search-{htmx}"),
    )
    parent = _create_parent("query-parent", "Query parent")
    _create_bundle("small-bundle", "Small bundle", parent, country="Small")
    for index in range(25):
        _create_bundle(
            f"large-bundle-{index}",
            f"Large bundle {index}",
            parent,
            country="Large",
        )
    ContentType.objects.get_for_model(Bundle)

    small_queries = _capture_search(
        client,
        "/search/bundles/",
        {"country": "Small"},
        htmx=htmx,
    )
    large_queries = _capture_search(
        client,
        "/search/bundles/",
        {"country": "Large"},
        htmx=htmx,
    )

    assert small_queries <= BUNDLE_QUERY_BUDGET
    assert large_queries == small_queries
