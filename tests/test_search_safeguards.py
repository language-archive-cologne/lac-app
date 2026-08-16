"""Database-backed coverage for bounded interactive search requests."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest
import yaml
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.views import View

from lacos.blam.models import Bundle
from lacos.blam.models import Collection
from lacos.explorer.facets import FACET_MAX_SELECTED_VALUES
from lacos.explorer.search_safeguards import SearchRequestBudgetMixin

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 25
RESULT_COUNT = 26


@pytest.mark.django_db
def test_over_budget_search_returns_controlled_422(client):
    response = client.get(
        "/search/",
        {
            "language": [
                f"language-{index}" for index in range(FACET_MAX_SELECTED_VALUES + 1)
            ],
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert b"too many facet selections" in response.content.lower()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "model", "context_name", "identifier_prefix"),
    [
        ("/search/", Collection, "collections", "C"),
        ("/search/bundles/", Bundle, "bundles", "B"),
    ],
)
def test_filtered_pagination_fetches_one_extra_row_without_exact_count(
    client,
    path,
    model,
    context_name,
    identifier_prefix,
):
    model.objects.bulk_create(
        [
            model(identifier=f"{identifier_prefix}{index:02d}")
            for index in range(RESULT_COUNT)
        ],
    )
    cache.clear()
    first_response = client.get(path)
    assert first_response.status_code == HTTPStatus.OK

    with CaptureQueriesContext(connection) as captured:
        response = client.get(path)

    assert response.status_code == HTTPStatus.OK
    assert len(response.context[context_name]) == PAGE_SIZE
    assert response.context["page_obj"].has_next()
    assert response.context["total_count"] == RESULT_COUNT
    assert response.context["total_count_is_lower_bound"] is True
    assert not any(
        query["sql"].lstrip().upper().startswith("SELECT COUNT(")
        for query in captured.captured_queries
    )


@pytest.mark.django_db
def test_countless_pagination_preserves_next_previous_and_htmx(client):
    Collection.objects.bulk_create(
        [Collection(identifier=f"C{index:02d}") for index in range(RESULT_COUNT)],
    )
    cache.clear()

    response = client.get("/search/", {"page": 2}, HTTP_HX_REQUEST="true")

    assert response.status_code == HTTPStatus.OK
    assert len(response.context["collections"]) == 1
    assert response.context["page_obj"].has_previous()
    assert not response.context["page_obj"].has_next()
    assert response.context["total_count"] == RESULT_COUNT


class _SlowSearchView(SearchRequestBudgetMixin, View):
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(0.05)")
        return HttpResponse("finished")


@override_settings(SEARCH_STATEMENT_TIMEOUT_MS=5)
@pytest.mark.django_db(transaction=True)
def test_database_timeout_returns_retryable_503():
    response = _SlowSearchView.as_view()(RequestFactory().get("/search/"))

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert response.headers["Retry-After"] == "5"
    assert b"temporarily unavailable" in response.content.lower()


@pytest.mark.parametrize(
    "compose_filename",
    ["docker-compose.dev.yml", "docker-compose.production.yml"],
)
def test_deployed_cache_redis_is_isolated_and_memory_bounded(compose_filename):
    compose = yaml.safe_load((REPO_ROOT / compose_filename).read_text())
    services = compose["services"]

    assert (
        services["django"]["environment"]["CACHE_REDIS_URL"] == "redis://cache:6379/0"
    )
    assert "cache" in services["django"]["depends_on"]
    assert "cache" in services["huey"]["depends_on"]
    cache_command = services["cache"]["command"]
    assert "--maxmemory 256mb" in cache_command
    assert "--maxmemory-policy allkeys-lru" in cache_command
    assert "--appendonly no" in cache_command

    production_settings = (
        REPO_ROOT / "config" / "settings" / "production.py"
    ).read_text()
    assert (
        'CACHE_REDIS_URL = env("CACHE_REDIS_URL", default=REDIS_URL)'
        in production_settings
    )
    assert '"LOCATION": CACHE_REDIS_URL' in production_settings
