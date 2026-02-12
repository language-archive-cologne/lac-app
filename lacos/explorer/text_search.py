"""Shared text-search helpers: FTS first, trigram fallback."""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, TrigramWordSimilarity
from django.db.models import QuerySet
from django.db.models.functions import Greatest


def build_fts_query(search_term: str) -> SearchQuery:
    """Build a prefix-matching full-text search query."""
    prefix_terms = " & ".join(f"{word}:*" for word in search_term.split())
    return SearchQuery(prefix_terms, config="simple", search_type="raw")


def apply_text_search(qs: QuerySet, search_term: str) -> QuerySet:
    """Apply FTS first; fall back to trigram if FTS returns nothing.

    Expects the queryset's model to have:
      - ``search_vector`` field (for FTS)
      - ``general_info__display_title`` (via FK)
      - ``identifier`` (from Repository base)
    """
    query = build_fts_query(search_term)
    fts_qs = qs.filter(search_vector=query)

    if fts_qs.exists():
        return fts_qs

    # Trigrams need at least 3 characters to be useful
    if len(search_term) < 3:
        return fts_qs  # empty

    return (
        qs.annotate(
            similarity=Greatest(
                TrigramWordSimilarity(search_term, "general_info__display_title"),
                TrigramWordSimilarity(search_term, "identifier"),
            )
        )
        .filter(similarity__gt=0.3)
        .distinct()
    )
