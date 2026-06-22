"""Search match reason helpers for explorer result pages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


def tokenize_match_query(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in query.split("|"):
        tokens.extend(t.lower() for t in part.split() if t.strip())
    return tuple(tokens)


def _text_matches_query(text: str, tokens: Iterable[str]) -> bool:
    if not text:
        return False
    token_tuple = tuple(tokens)
    if not token_tuple:
        return False
    lowered = text.lower()
    words = re.findall(r"\w+", lowered)
    return any(
        token in lowered or any(word.startswith(token) for word in words)
        for token in token_tuple
    )


def _dedupe(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _append_general_info_reasons(
    bundle,
    tokens: tuple[str, ...],
    reasons: list[str],
) -> None:
    gi = getattr(bundle, "get_general_info", None)
    if not gi:
        return

    if _text_matches_query(getattr(gi, "display_title", ""), tokens):
        reasons.append("title")
    if _text_matches_query(getattr(gi, "description", ""), tokens):
        reasons.append("description")
    keywords = getattr(gi, "keywords", None)
    if keywords and any(
        _text_matches_query(getattr(kw, "value", ""), tokens)
        for kw in keywords.all()
    ):
        reasons.append("keyword")
    location = getattr(gi, "location", None)
    if location and (
        _text_matches_query(getattr(location, "country_name", ""), tokens)
        or _text_matches_query(getattr(location, "country_facet", ""), tokens)
    ):
        reasons.append("country")
    object_languages = getattr(gi, "object_languages", None)
    if object_languages and any(
        _text_matches_query(getattr(lang, "name", ""), tokens)
        or _text_matches_query(getattr(lang, "display_name", ""), tokens)
        for lang in object_languages.all()
    ):
        reasons.append("language")


def _append_structural_reasons(
    bundle,
    tokens: tuple[str, ...],
    reasons: list[str],
) -> None:
    si = getattr(bundle, "get_structural_info", None)
    if not si or not getattr(si, "is_member_of_collection", None):
        return

    parent = si.is_member_of_collection
    if _text_matches_query(getattr(parent, "identifier", ""), tokens):
        reasons.append("parent collection identifier")
    parent_gi = getattr(parent, "get_general_info", None)
    if parent_gi and _text_matches_query(
        getattr(parent_gi, "display_title", ""),
        tokens,
    ):
        reasons.append("parent collection title")


def _contributor_matches(contributor, tokens: tuple[str, ...]) -> bool:
    contributor_name = getattr(contributor, "contributor_name", None)
    return (
        _text_matches_query(getattr(contributor, "family_name", ""), tokens)
        or _text_matches_query(getattr(contributor, "given_name", ""), tokens)
        or _text_matches_query(getattr(contributor, "role", ""), tokens)
        or (
            contributor_name
            and (
                _text_matches_query(
                    getattr(contributor_name, "contributor_family_name", ""),
                    tokens,
                )
                or _text_matches_query(
                    getattr(contributor_name, "contributor_given_name", ""),
                    tokens,
                )
            )
        )
    )


def _append_publication_reasons(
    bundle,
    tokens: tuple[str, ...],
    reasons: list[str],
) -> None:
    pub = getattr(bundle, "get_publication_info", None)
    if not pub:
        return

    if _text_matches_query(getattr(pub, "data_provider", ""), tokens):
        reasons.append("data provider")
    if any(
        _text_matches_query(getattr(creator, "family_name", ""), tokens)
        or _text_matches_query(getattr(creator, "given_name", ""), tokens)
        for creator in pub.creators.all()
    ):
        reasons.append("creator")
    if any(
        _contributor_matches(contributor, tokens)
        for contributor in pub.contributors.all()
    ):
        reasons.append("contributor")


def bundle_match_reasons_for_tokens(bundle, tokens: Iterable[str]) -> tuple[str, ...]:
    """Infer matched bundle fields for already-tokenized search input."""
    token_tuple = tuple(tokens)
    if not token_tuple:
        return ()

    reasons: list[str] = []
    if _text_matches_query(getattr(bundle, "identifier", ""), token_tuple):
        reasons.append("identifier")

    _append_general_info_reasons(bundle, token_tuple, reasons)
    _append_structural_reasons(bundle, token_tuple, reasons)
    _append_publication_reasons(bundle, token_tuple, reasons)

    return _dedupe(reasons)


def bundle_match_reasons(bundle, query: str) -> tuple[str, ...]:
    return bundle_match_reasons_for_tokens(
        bundle,
        tokenize_match_query((query or "").strip()),
    )


def bundle_match_reasons_csv(bundle, query: str) -> str:
    return ", ".join(bundle_match_reasons(bundle, query))


def attach_bundle_match_reasons(bundles, query: str) -> None:
    tokens = tokenize_match_query((query or "").strip())
    for bundle in bundles:
        bundle.search_match_reasons = bundle_match_reasons_for_tokens(bundle, tokens)
