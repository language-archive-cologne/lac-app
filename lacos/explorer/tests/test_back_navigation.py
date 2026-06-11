"""Tests for back-to-search-results navigation tags."""
from __future__ import annotations
from urllib.parse import unquote
from django.test import RequestFactory
from django.urls import reverse
from lacos.explorer.templatetags.explorer_extras import back_query, safe_back_url


def _ctx(request):
    return {"request": request}


def test_back_query_round_trips():
    req = RequestFactory().get("/search/", {"q": "rock art"})
    out = back_query(_ctx(req))
    assert out.startswith("?back=")
    assert unquote(out[len("?back="):]) == "/search/?q=rock+art"


def test_back_query_without_request_is_empty():
    assert back_query({}) == ""


def test_safe_back_url_accepts_search_path():
    back = reverse("faceted_search") + "?q=test"
    req = RequestFactory().get("/c/h", {"back": back})
    assert safe_back_url(_ctx(req)) == back


def test_safe_back_url_accepts_bundle_search():
    back = reverse("bundle_faceted_search")
    req = RequestFactory().get("/c/h", {"back": back})
    assert safe_back_url(_ctx(req)) == back


def test_safe_back_url_rejects_foreign():
    req = RequestFactory().get("/c/h", {"back": "https://evil.com/x"})
    assert safe_back_url(_ctx(req)) == ""


def test_safe_back_url_rejects_protocol_relative():
    req = RequestFactory().get("/c/h", {"back": "//evil.com/x"})
    assert safe_back_url(_ctx(req)) == ""


def test_safe_back_url_rejects_non_search_path():
    req = RequestFactory().get("/c/h", {"back": reverse("explorer:collection_list")})
    assert safe_back_url(_ctx(req)) == ""


def test_safe_back_url_missing_is_empty():
    req = RequestFactory().get("/c/h")
    assert safe_back_url(_ctx(req)) == ""
