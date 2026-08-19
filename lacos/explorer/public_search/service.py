"""Application boundary for anonymous public-index searches."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse

from lacos.explorer.advanced_search import BUNDLE_FIELD_DEFINITIONS
from lacos.explorer.advanced_search import COLLECTION_FIELD_DEFINITIONS
from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.facets import FACET_DEFINITIONS
from lacos.explorer.public_search.query import PublicSearchQueryEngine
from lacos.explorer.public_search.store import load_public_search_index

PUBLIC_SEARCH_SCOPES = {
    "collections": (FACET_DEFINITIONS, COLLECTION_FIELD_DEFINITIONS),
    "bundles": (BUNDLE_FACET_DEFINITIONS, BUNDLE_FIELD_DEFINITIONS),
}


def is_anonymous_public_search(request) -> bool:
    return bool(
        settings.PUBLIC_SEARCH_INDEX_ENABLED and not request.user.is_authenticated,
    )


def search_public_index(scope: str, params):
    definitions, field_definitions = PUBLIC_SEARCH_SCOPES[scope]
    index = load_public_search_index(Path(settings.PUBLIC_SEARCH_INDEX_PATH))
    return PublicSearchQueryEngine(
        records=index[scope],
        definitions=definitions,
        version=index["version"],
        field_keys={definition.key for definition in field_definitions},
    ).search(params)


def public_search_unavailable_response() -> HttpResponse:
    response = HttpResponse(
        "Public search is temporarily unavailable.\n",
        status=503,
        content_type="text/plain; charset=utf-8",
    )
    response.headers["Retry-After"] = "30"
    return response
