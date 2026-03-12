"""Shared text-search helpers based on PostgreSQL full-text search."""

from __future__ import annotations

import re
import unicodedata

from django.contrib.postgres.search import SearchQuery
from django.db.models import QuerySet


def sanitize_search_term(term: str) -> str:
    """Normalize and sanitize a search term for use in tsquery.

    Applies Unicode NFC normalization (to match NFC-normalized stored data)
    and strips all non-word characters to prevent tsquery syntax errors.
    """
    normalized = unicodedata.normalize("NFC", term.strip())
    return re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)


def _expand_prefix_variants(word: str) -> list[str]:
    variants = {word}
    if len(word) > 3 and word.endswith("y"):
        variants.add(f"{word[:-1]}ies")
    if len(word) > 4 and word.endswith("ies"):
        variants.add(f"{word[:-3]}y")
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        variants.add(word[:-1])
    return sorted(variants)


def build_fts_query(search_term: str) -> SearchQuery | None:
    """Build a prefix-matching full-text search query.

    Returns None if the search term contains no searchable words.
    """
    sanitized = sanitize_search_term(search_term)
    words = sanitized.split()
    if not words:
        return None
    prefix_terms = " & ".join(
        "(" + " | ".join(f"{variant}:*" for variant in _expand_prefix_variants(word)) + ")"
        for word in words
    )
    return SearchQuery(prefix_terms, config="simple", search_type="raw")


def apply_text_search(qs: QuerySet, search_term: str) -> QuerySet:
    """Apply prefix-matching full-text search."""
    query = build_fts_query(search_term)
    if query is None:
        return qs.none()
    return qs.filter(search_vector=query)
