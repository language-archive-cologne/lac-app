"""Cacheable delivery of the generated public search artifact."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.http import HttpResponseNotModified

from lacos.explorer.public_search.store import PublicSearchIndexError
from lacos.explorer.public_search.store import load_public_search_index


def public_search_index_view(request):
    if not settings.PUBLIC_SEARCH_INDEX_ENABLED:
        return HttpResponse(status=HTTPStatus.NOT_FOUND)
    path = Path(settings.PUBLIC_SEARCH_INDEX_PATH)
    try:
        index = load_public_search_index(path)
    except (OSError, PublicSearchIndexError):
        response = HttpResponse(
            "Public search index is temporarily unavailable.\n",
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="text/plain; charset=utf-8",
        )
        response.headers["Retry-After"] = "30"
        return response

    etag = f'"{index["version"]}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = HttpResponse(path.read_bytes(), content_type="application/json")
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = (
        f"public, max-age={settings.PUBLIC_SEARCH_INDEX_CACHE_SECONDS}"
    )
    return response
