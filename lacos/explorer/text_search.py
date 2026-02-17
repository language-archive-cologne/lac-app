"""Shared text-search helpers based on PostgreSQL full-text search."""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery
from django.db.models import QuerySet


def build_fts_query(search_term: str) -> SearchQuery:
    """Build a prefix-matching full-text search query."""
    prefix_terms = " & ".join(f"{word}:*" for word in search_term.split())
    return SearchQuery(prefix_terms, config="simple", search_type="raw")


def apply_text_search(qs: QuerySet, search_term: str) -> QuerySet:
    """Apply prefix-matching full-text search."""
    query = build_fts_query(search_term)
    return qs.filter(search_vector=query)
