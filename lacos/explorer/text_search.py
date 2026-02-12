"""Shared text-search helpers: FTS combined with trigram similarity."""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, TrigramWordSimilarity
from django.db.models import Q, QuerySet
from django.db.models.functions import Greatest


def build_fts_query(search_term: str) -> SearchQuery:
    """Build a prefix-matching full-text search query."""
    prefix_terms = " & ".join(f"{word}:*" for word in search_term.split())
    return SearchQuery(prefix_terms, config="simple", search_type="raw")


def apply_text_search(qs: QuerySet, search_term: str) -> QuerySet:
    """Apply FTS combined with trigram similarity for typo tolerance.

    For queries < 3 chars: FTS only (trigrams need at least 3 chars).
    For queries >= 3 chars: FTS OR trigram match, so both exact prefix
    matches and fuzzy matches are returned together.
    """
    query = build_fts_query(search_term)

    if len(search_term) < 3:
        return qs.filter(search_vector=query)

    return (
        qs.annotate(
            similarity=Greatest(
                TrigramWordSimilarity(search_term, "general_info__display_title"),
                TrigramWordSimilarity(search_term, "identifier"),
            )
        )
        .filter(Q(search_vector=query) | Q(similarity__gt=0.3))
        .distinct()
    )
