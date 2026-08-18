"""Integration coverage for ALTCHA-gated faceted search access."""

from __future__ import annotations

import base64
import json
from http import HTTPStatus
from unittest.mock import patch

import altcha
import pytest
from django.core import signing
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from lacos.explorer.search_access import SEARCH_ACCESS_SIGNING_SALT
from lacos.explorer.search_capacity import SEARCH_CAPACITY_CACHE_KEY
from lacos.storage.services.altcha_service import get_altcha_service

SEARCH_ACCESS_SETTINGS = {
    "SEARCH_ALTCHA_ENABLED": True,
    "SEARCH_ALTCHA_ACCESS_TTL_SECONDS": 600,
    "SEARCH_ALTCHA_REQUEST_BUDGET": 2,
    "SEARCH_ALTCHA_VERIFY_RATE_LIMIT": 10,
    "SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS": 60,
    "SEARCH_MAX_CONCURRENT_REQUESTS": 2,
    "SEARCH_CAPACITY_SLOT_TIMEOUT_SECONDS": 40,
    "SEARCH_CAPACITY_RETRY_SECONDS": 5,
}


def _solved_altcha_payload() -> str:
    service = get_altcha_service()
    challenge = service.create_challenge()
    solution = altcha.solve_challenge(
        challenge=challenge["challenge"],
        salt=challenge["salt"],
        algorithm=challenge["algorithm"],
        max_number=challenge["maxnumber"],
        start=0,
    )
    payload = {
        "algorithm": challenge["algorithm"],
        "challenge": challenge["challenge"],
        "number": solution.number,
        "salt": challenge["salt"],
        "signature": challenge["signature"],
    }
    encoded = json.dumps(payload).encode()
    return base64.b64encode(encoded).decode()


@pytest.fixture(autouse=True)
def _isolated_cache():
    cache.clear()
    yield
    cache.clear()


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_filtered_search_redirects_before_database_work(client):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("faceted_search"), {"keyword": "DoBeS"})

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    assert "next=%2Fsearch%2F%3Fkeyword%3DDoBeS" in response.url
    statements = "\n".join(query["sql"] for query in queries.captured_queries)
    assert "statement_timeout" not in statements
    assert "blam_collection" not in statements


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_forged_cookie_redirects_before_database_work(client):
    client.cookies["lacos_search_access"] = "publicly-forged-cookie"
    cache.set(SEARCH_CAPACITY_CACHE_KEY, 2, timeout=40)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("faceted_search"), {"keyword": "DoBeS"})

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    statements = "\n".join(query["sql"] for query in queries.captured_queries)
    assert "statement_timeout" not in statements
    assert "blam_collection" not in statements
    assert (
        cache.get(SEARCH_CAPACITY_CACHE_KEY)
        == SEARCH_ACCESS_SETTINGS["SEARCH_MAX_CONCURRENT_REQUESTS"]
    )


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
@pytest.mark.parametrize("route_name", ["faceted_search", "bundle_faceted_search"])
def test_bare_search_redirects_before_database_work(client, route_name):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse(route_name))

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))
    statements = "\n".join(query["sql"] for query in queries.captured_queries)
    assert "statement_timeout" not in statements
    assert "blam_collection" not in statements
    assert "blam_bundle" not in statements


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_htmx_search_redirects_to_full_verification_page(client):
    response = client.get(
        reverse("bundle_faceted_search"),
        {"file_type": "wav"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.headers["HX-Redirect"].startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_access_page_renders_private_proof_of_work_widget(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    response = client.get(reverse("search_access"), {"next": target})

    content = response.content.decode()
    assert response.status_code == HTTPStatus.OK
    assert "<altcha-widget" in content
    assert reverse("storage:altcha_challenge") in content
    assert 'name="next" value="/search/?keyword=DoBeS"' in content


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_valid_solution_issues_bound_limited_search_grant(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    response = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
        REMOTE_ADDR="192.0.2.10",
        HTTP_USER_AGENT="test-browser",
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url == target
    grant = response.cookies["lacos_search_access"]
    assert grant["httponly"] is True
    assert grant["samesite"] == "Lax"
    assert (
        int(grant["max-age"])
        == SEARCH_ACCESS_SETTINGS["SEARCH_ALTCHA_ACCESS_TTL_SECONDS"]
    )

    first = client.get(
        target,
        REMOTE_ADDR="192.0.2.10",
        HTTP_USER_AGENT="test-browser",
    )
    second = client.get(
        target,
        REMOTE_ADDR="192.0.2.10",
        HTTP_USER_AGENT="test-browser",
    )
    exhausted = client.get(
        target,
        REMOTE_ADDR="192.0.2.10",
        HTTP_USER_AGENT="test-browser",
    )

    assert first.status_code == HTTPStatus.OK
    assert second.status_code == HTTPStatus.OK
    assert exhausted.status_code == HTTPStatus.FOUND
    assert exhausted.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_grant_cannot_move_to_another_client_address(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
        REMOTE_ADDR="192.0.2.10",
        HTTP_USER_AGENT="test-browser",
    )
    assert issued.status_code == HTTPStatus.FOUND

    response = client.get(
        target,
        REMOTE_ADDR="192.0.2.11",
        HTTP_USER_AGENT="test-browser",
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_malformed_signed_grant_fails_closed(client):
    client.cookies["lacos_search_access"] = signing.dumps(
        ["not", "a", "grant"],
        salt=SEARCH_ACCESS_SIGNING_SALT,
    )

    response = client.get(reverse("faceted_search"), {"keyword": "DoBeS"})

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_grant_fails_closed_when_cache_counter_is_unavailable(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
    )
    assert issued.status_code == HTTPStatus.FOUND

    with patch("lacos.explorer.search_access.cache") as grant_cache:
        grant_cache.get.return_value = 0
        grant_cache.incr.return_value = None
        response = client.get(target)

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_grant_fails_closed_when_cache_counter_raises(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
    )
    assert issued.status_code == HTTPStatus.FOUND

    with patch("lacos.explorer.search_access.cache") as grant_cache:
        grant_cache.get.return_value = 0
        grant_cache.incr.side_effect = RuntimeError("cache unavailable")
        response = client.get(target)

    assert response.status_code == HTTPStatus.FOUND
    assert response.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_verified_search_uses_aggregate_capacity_after_grant_validation(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
    )
    assert issued.status_code == HTTPStatus.FOUND
    cache.set(SEARCH_CAPACITY_CACHE_KEY, 2, timeout=40)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(target)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "5"
    statements = "\n".join(query["sql"] for query in queries.captured_queries)
    assert "statement_timeout" not in statements
    assert "blam_collection" not in statements


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_capacity_rejection_does_not_spend_the_search_grant(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
    )
    assert issued.status_code == HTTPStatus.FOUND
    cache.set(SEARCH_CAPACITY_CACHE_KEY, 2, timeout=40)

    at_capacity = client.get(target)

    assert at_capacity.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    cache.delete(SEARCH_CAPACITY_CACHE_KEY)
    assert client.get(target).status_code == HTTPStatus.OK
    assert client.get(target).status_code == HTTPStatus.OK
    exhausted = client.get(target)
    assert exhausted.status_code == HTTPStatus.FOUND
    assert exhausted.url.startswith(reverse("search_access"))


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_verified_search_fails_closed_when_capacity_is_unavailable(client):
    target = f"{reverse('faceted_search')}?keyword=DoBeS"
    issued = client.post(
        reverse("search_access"),
        {"altcha": _solved_altcha_payload(), "next": target},
    )
    assert issued.status_code == HTTPStatus.FOUND

    with patch(
        "lacos.explorer.search_capacity.SearchCapacityService.acquire",
        return_value=False,
    ):
        response = client.get(target)

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "5"


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_invalid_solution_fails_closed_without_cookie(client):
    response = client.post(
        reverse("search_access"),
        {"altcha": "not-a-solution", "next": reverse("faceted_search")},
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert "lacos_search_access" not in response.cookies
    assert "Verification failed" in response.content.decode()


@override_settings(
    **{
        **SEARCH_ACCESS_SETTINGS,
        "SEARCH_ALTCHA_VERIFY_RATE_LIMIT": 1,
        "SEARCH_ALTCHA_VERIFY_RATE_WINDOW_SECONDS": 60,
    },
)
@pytest.mark.django_db
def test_verification_attempts_are_rate_limited_per_client(client):
    url = reverse("search_access")
    form = {"altcha": "not-a-solution", "next": reverse("faceted_search")}

    first = client.post(url, form, REMOTE_ADDR="192.0.2.20")
    limited = client.post(url, form, REMOTE_ADDR="192.0.2.20")

    assert first.status_code == HTTPStatus.FORBIDDEN
    assert limited.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert "Too many verification attempts" in limited.content.decode()


@override_settings(**SEARCH_ACCESS_SETTINGS)
@pytest.mark.django_db
def test_access_redirect_rejects_external_next_url(client):
    response = client.post(
        reverse("search_access"),
        {
            "altcha": _solved_altcha_payload(),
            "next": "https://attacker.example/steal",
        },
    )

    assert response.status_code == HTTPStatus.FOUND
    assert response.url == reverse("faceted_search")
