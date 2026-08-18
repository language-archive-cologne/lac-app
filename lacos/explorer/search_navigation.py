"""Validation helpers for navigation between faceted search and detail pages."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.urls import Resolver404
from django.urls import resolve
from django.utils.http import url_has_allowed_host_and_scheme

SEARCH_VIEW_NAMES = {
    "faceted_search",
    "field_search",
    "bundle_faceted_search",
    "bundle_field_search",
}
SEARCH_RESULT_DETAIL_VIEW_NAMES = {
    "bundle_detail",
    "bundle_detail_by_handle",
    "collection_detail",
    "collection_detail_by_handle",
}


def _local_view_name(request, candidate: str | None) -> str | None:
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate or not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None

    try:
        return resolve(urlsplit(candidate).path).url_name
    except Resolver404:
        return None


def validated_search_back_url(request, candidate: str | None) -> str:
    """Return a local faceted-search URL or an empty string."""
    if _local_view_name(request, candidate) not in SEARCH_VIEW_NAMES:
        return ""
    return candidate.strip() if candidate else ""


def is_search_access_target(request, candidate: str | None) -> bool:
    """Return whether ALTCHA may redirect to this local search-flow URL."""
    return _local_view_name(request, candidate) in (
        SEARCH_VIEW_NAMES | SEARCH_RESULT_DETAIL_VIEW_NAMES
    )
