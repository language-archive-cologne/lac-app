"""Regression coverage for crawler-followed search result detail requests."""

from __future__ import annotations

from http import HTTPStatus
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from lacos.explorer.search_access import SEARCH_ACCESS_COOKIE_NAME
from lacos.explorer.search_access import get_search_access_service
from lacos.explorer.search_capacity import SEARCH_CAPACITY_CACHE_KEY

SEARCH_NAVIGATION_SETTINGS = {
    "SEARCH_ALTCHA_ENABLED": True,
    "SEARCH_ALTCHA_ACCESS_TTL_SECONDS": 600,
    "SEARCH_GRANT_RATE_LIMIT": 20,
    "SEARCH_GRANT_RATE_WINDOW_SECONDS": 60,
    "SEARCH_MAX_CONCURRENT_REQUESTS": 2,
    "SEARCH_CAPACITY_SLOT_TIMEOUT_SECONDS": 40,
    "SEARCH_CAPACITY_RETRY_SECONDS": 5,
}
CLIENT_ADDRESS = "192.0.2.40"
CLIENT_USER_AGENT = "search-navigation-test"


def _application_queries(queries) -> list[str]:
    return [
        query["sql"]
        for query in queries.captured_queries
        if not query["sql"].startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))
    ]


@pytest.fixture(autouse=True)
def _isolated_cache():
    cache.clear()
    yield
    cache.clear()


def _issue_grant(client) -> None:
    request = RequestFactory().get(
        "/search/",
        REMOTE_ADDR=CLIENT_ADDRESS,
        HTTP_USER_AGENT=CLIENT_USER_AGENT,
    )
    grant = get_search_access_service().issue(request)
    client.cookies[SEARCH_ACCESS_COOKIE_NAME] = grant.value


@override_settings(**SEARCH_NAVIGATION_SETTINGS)
@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "route_kwargs", "back_path"),
    [
        (
            "explorer:bundle_detail",
            {"pk": uuid4()},
            "/search/bundles/?keyword=Conversation",
        ),
        (
            "explorer:collection_detail",
            {"pk": uuid4()},
            "/search/?country=Germany",
        ),
    ],
)
def test_search_result_detail_requires_grant_before_database_work(
    client,
    route_name,
    route_kwargs,
    back_path,
):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse(route_name, kwargs=route_kwargs),
            {"back": back_path},
            REMOTE_ADDR=CLIENT_ADDRESS,
            HTTP_USER_AGENT=CLIENT_USER_AGENT,
        )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    assert "next=" in response.url
    assert _application_queries(queries) == []


@override_settings(**SEARCH_NAVIGATION_SETTINGS)
@pytest.mark.django_db
def test_valid_grant_allows_search_result_detail_to_reach_lookup(client):
    _issue_grant(client)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("explorer:bundle_detail", kwargs={"pk": uuid4()}),
            {"back": "/search/bundles/?keyword=Conversation"},
            REMOTE_ADDR=CLIENT_ADDRESS,
            HTTP_USER_AGENT=CLIENT_USER_AGENT,
        )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert _application_queries(queries)


@override_settings(**SEARCH_NAVIGATION_SETTINGS)
@pytest.mark.django_db
def test_direct_detail_without_search_back_remains_public(client):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("explorer:bundle_detail", kwargs={"pk": uuid4()}),
            REMOTE_ADDR=CLIENT_ADDRESS,
            HTTP_USER_AGENT=CLIENT_USER_AGENT,
        )

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert _application_queries(queries)


@override_settings(**SEARCH_NAVIGATION_SETTINGS)
@pytest.mark.django_db
def test_forged_grant_fails_before_detail_lookup(client):
    client.cookies[SEARCH_ACCESS_COOKIE_NAME] = "forged"

    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("explorer:bundle_detail", kwargs={"pk": uuid4()}),
            {"back": "/search/bundles/?keyword=Conversation"},
            REMOTE_ADDR=CLIENT_ADDRESS,
            HTTP_USER_AGENT=CLIENT_USER_AGENT,
        )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    assert _application_queries(queries) == []


@override_settings(
    **{
        **SEARCH_NAVIGATION_SETTINGS,
        "SEARCH_GRANT_RATE_LIMIT": 2,
    },
)
@pytest.mark.django_db
def test_search_result_details_spend_the_grant_rate_allowance(client):
    _issue_grant(client)
    url = reverse("explorer:bundle_detail", kwargs={"pk": uuid4()})
    request_kwargs = {
        "data": {"back": "/search/bundles/?keyword=Conversation"},
        "REMOTE_ADDR": CLIENT_ADDRESS,
        "HTTP_USER_AGENT": CLIENT_USER_AGENT,
    }

    assert client.get(url, **request_kwargs).status_code == HTTPStatus.NOT_FOUND
    assert client.get(url, **request_kwargs).status_code == HTTPStatus.NOT_FOUND
    with CaptureQueriesContext(connection) as queries:
        limited = client.get(url, **request_kwargs)

    assert limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert limited.headers["Retry-After"] == "60"
    assert _application_queries(queries) == []


@override_settings(**SEARCH_NAVIGATION_SETTINGS)
@pytest.mark.django_db
def test_search_result_detail_respects_shared_search_capacity(client):
    _issue_grant(client)
    cache.set(SEARCH_CAPACITY_CACHE_KEY, 2, timeout=40)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(
            reverse("explorer:bundle_detail", kwargs={"pk": uuid4()}),
            {"back": "/search/bundles/?keyword=Conversation"},
            REMOTE_ADDR=CLIENT_ADDRESS,
            HTTP_USER_AGENT=CLIENT_USER_AGENT,
        )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "5"
    assert _application_queries(queries) == []
