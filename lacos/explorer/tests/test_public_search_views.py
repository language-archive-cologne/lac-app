"""Anonymous view integration for the public search index."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from lacos.explorer.public_search.builder import build_public_search_index
from lacos.explorer.public_search.store import clear_public_search_index_cache
from lacos.explorer.public_search.store import write_public_search_index
from lacos.explorer.search_access import SEARCH_ACCESS_COOKIE_NAME
from lacos.explorer.search_access import get_search_access_service
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_bundle_facets import _create_collection


@pytest.fixture(autouse=True)
def _clear_index_cache():
    cache.clear()
    clear_public_search_index_cache()
    yield
    cache.clear()
    clear_public_search_index_cache()


@pytest.fixture
def public_index_path(tmp_path):
    collection = _create_collection("test-collection", "Test Collection")
    _create_bundle(
        "test-bundle",
        "Akan Stories",
        collection,
        languages=[("Akan", "aka")],
        country="Ghana",
    )
    target = tmp_path / "public-search.json"
    write_public_search_index(target, build_public_search_index())
    return target


PUBLIC_INDEX_SETTINGS = {
    "PUBLIC_SEARCH_INDEX_ENABLED": True,
    "SEARCH_ALTCHA_ENABLED": True,
    "SEARCH_ALTCHA_ACCESS_TTL_SECONDS": 600,
    "SEARCH_ALTCHA_VERIFY_RATE_LIMIT": 10,
    "SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS": 60,
    "SEARCH_GRANT_RATE_LIMIT": 20,
    "SEARCH_GRANT_RATE_WINDOW_SECONDS": 60,
    "SEARCH_MAX_CONCURRENT_REQUESTS": 8,
    "SEARCH_CAPACITY_SLOT_TIMEOUT_SECONDS": 40,
    "SEARCH_CAPACITY_RETRY_SECONDS": 5,
}


def _grant_search_access(client) -> None:
    request = RequestFactory().get(reverse("bundle_faceted_search"))
    grant = get_search_access_service().issue(request)
    client.cookies[SEARCH_ACCESS_COOKIE_NAME] = grant.value


@pytest.mark.django_db
def test_anonymous_filtered_search_requires_grant_before_public_index_work(
    client,
    tmp_path,
):
    missing = tmp_path / "missing.json"

    with (
        override_settings(
            **PUBLIC_INDEX_SETTINGS,
            PUBLIC_SEARCH_INDEX_PATH=missing,
        ),
        CaptureQueriesContext(connection) as captured,
    ):
        response = client.get(
            reverse("bundle_faceted_search"),
            {"language": "aka"},
        )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    assert "next=%2Fsearch%2Fbundles%2F%3Flanguage%3Daka" in response.url
    assert captured.captured_queries == []


@pytest.mark.django_db
def test_verified_anonymous_search_uses_index_without_database_queries(
    client,
    public_index_path,
):
    with override_settings(
        **PUBLIC_INDEX_SETTINGS,
        PUBLIC_SEARCH_INDEX_PATH=public_index_path,
    ):
        _grant_search_access(client)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(
                reverse("bundle_faceted_search"),
                {"language": "aka"},
            )
            content = response.content.decode()

    assert response.status_code == HTTPStatus.OK
    assert "Akan Stories" in content
    assert response.context["public_search_index"] is True
    assert response.context["total_count"] == 1
    assert captured.captured_queries == []
    assert response.headers["X-Search-Backend"] == "public-index"


@pytest.mark.django_db
def test_anonymous_htmx_search_requires_grant_before_public_index_work(
    client,
    tmp_path,
):
    missing = tmp_path / "missing.json"

    with override_settings(
        **PUBLIC_INDEX_SETTINGS,
        PUBLIC_SEARCH_INDEX_PATH=missing,
    ):
        response = client.get(
            reverse("bundle_faceted_search"),
            {"country": "Ghana"},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.headers["HX-Redirect"].startswith(reverse("search_access"))


@pytest.mark.django_db
def test_verified_anonymous_htmx_search_uses_public_index_fragment(
    client,
    public_index_path,
):
    with override_settings(
        **PUBLIC_INDEX_SETTINGS,
        PUBLIC_SEARCH_INDEX_PATH=public_index_path,
    ):
        _grant_search_access(client)
        response = client.get(
            reverse("bundle_faceted_search"),
            {"country": "Ghana"},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == HTTPStatus.OK
    assert "Akan Stories" in response.content.decode()
    assert "<html" not in response.content.decode()
    assert response.headers["X-Search-Backend"] == "public-index"


@pytest.mark.django_db
def test_anonymous_public_index_search_respects_grant_rate_limit(
    client,
    public_index_path,
):
    with override_settings(
        **{
            **PUBLIC_INDEX_SETTINGS,
            "PUBLIC_SEARCH_INDEX_PATH": public_index_path,
            "SEARCH_GRANT_RATE_LIMIT": 1,
        },
    ):
        _grant_search_access(client)
        admitted = client.get(
            reverse("bundle_faceted_search"),
            {"country": "Ghana"},
        )
        rate_limited = client.get(
            reverse("bundle_faceted_search"),
            {"language": "aka"},
        )

    assert admitted.status_code == HTTPStatus.OK
    assert rate_limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert rate_limited.headers["Retry-After"] == "60"


@pytest.mark.django_db
def test_anonymous_landing_facets_come_from_index_without_cache_or_database(
    client,
    public_index_path,
):
    cache.clear()

    with (
        override_settings(
            **PUBLIC_INDEX_SETTINGS,
            PUBLIC_SEARCH_INDEX_PATH=public_index_path,
        ),
        CaptureQueriesContext(connection) as captured,
    ):
        response = client.get(reverse("bundle_faceted_search"))

    language_facet = next(
        facet for facet in response.context["facets"] if facet.name == "language"
    )
    assert response.status_code == HTTPStatus.OK
    assert response.context["search_shell"] is True
    assert response.context["public_search_index"] is True
    assert [(value.value, value.label) for value in language_facet.values] == [
        ("aka", "Akan"),
    ]
    assert captured.captured_queries == []


@pytest.mark.django_db
def test_missing_public_index_fails_closed_without_database_fallback(client, tmp_path):
    missing = tmp_path / "missing.json"

    with override_settings(
        **PUBLIC_INDEX_SETTINGS,
        PUBLIC_SEARCH_INDEX_PATH=missing,
    ):
        _grant_search_access(client)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(
                reverse("bundle_faceted_search"),
                {"country": "Ghana"},
            )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "30"
    assert captured.captured_queries == []


@pytest.mark.django_db
def test_missing_public_index_landing_shell_fails_closed(client, tmp_path):
    missing = tmp_path / "missing.json"

    with (
        override_settings(
            **PUBLIC_INDEX_SETTINGS,
            PUBLIC_SEARCH_INDEX_PATH=missing,
        ),
        CaptureQueriesContext(connection) as captured,
    ):
        response = client.get(reverse("bundle_faceted_search"))

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "30"
    assert captured.captured_queries == []


@pytest.mark.django_db
def test_authenticated_search_keeps_database_backend(
    client,
    django_user_model,
    public_index_path,
):
    client.force_login(django_user_model.objects.create_user(username="search-user"))

    with (
        override_settings(
            PUBLIC_SEARCH_INDEX_ENABLED=True,
            PUBLIC_SEARCH_INDEX_PATH=public_index_path,
            SEARCH_ALTCHA_ENABLED=False,
        ),
        CaptureQueriesContext(connection) as captured,
    ):
        response = client.get(
            reverse("bundle_faceted_search"),
            {"country": "Ghana"},
        )
        _ = response.content

    assert response.status_code == HTTPStatus.OK
    assert response.context.get("public_search_index") is not True
    assert any("blam_bundle" in query["sql"] for query in captured.captured_queries)


@pytest.mark.django_db
def test_public_index_endpoint_is_cacheable_and_supports_etag(
    client,
    public_index_path,
):
    with (
        override_settings(
            PUBLIC_SEARCH_INDEX_ENABLED=True,
            PUBLIC_SEARCH_INDEX_PATH=public_index_path,
        ),
        CaptureQueriesContext(connection) as captured,
    ):
        first = client.get(reverse("public_search_index"))
        second = client.get(
            reverse("public_search_index"),
            HTTP_IF_NONE_MATCH=first.headers["ETag"],
        )

    assert first.status_code == HTTPStatus.OK
    assert first.headers["Cache-Control"].startswith("public,")
    assert first.headers["Content-Type"] == "application/json"
    assert second.status_code == HTTPStatus.NOT_MODIFIED
    assert captured.captured_queries == []
