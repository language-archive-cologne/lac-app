"""Pure query behavior for the public search index."""

from __future__ import annotations

import pytest
from django.http import QueryDict

from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.facets import FacetSelectionLimitError
from lacos.explorer.public_search.query import PublicSearchQueryEngine

EXPECTED_FILTERED_RECORDS = 2


def _record(  # noqa: PLR0913 -- explicit test data keeps cases readable.
    identifier: str,
    title: str,
    *,
    language: tuple[str, str],
    country: str,
    keywords: list[str] | None = None,
    collection: str = "Collection",
):
    return {
        "identifier": identifier,
        "handle_path": identifier,
        "title": title,
        "description": f"Description for {title}",
        "keywords": keywords or [],
        "languages": [{"code": language[0], "name": language[1]}],
        "location": {
            "name": "",
            "country": country,
            "region": "",
            "geo": "",
        },
        "publication": {
            "year": 2024,
            "provider": "Provider",
            "creators": [],
            "contributors": [],
        },
        "grant_ids": [],
        "acl_access_level": "public",
        "licenses": [],
        "file_types": [],
        "collection": {
            "identifier": collection,
            "handle_path": collection,
            "title": collection,
        },
        "facets": {
            "keyword": keywords or [],
            "language": [language[0]],
            "file_type": [],
            "collection": [collection],
            "year": ["2024"],
            "country": [country],
            "region": [],
            "access": ["public"],
            "license": [],
        },
    }


def _engine() -> PublicSearchQueryEngine:
    return PublicSearchQueryEngine(
        records=[
            _record(
                "bundle-b",
                "Beta narratives",
                language=("aka", "Akan"),
                country="Ghana",
                keywords=["narrative"],
                collection="Collection B",
            ),
            _record(
                "bundle-a",
                "Alpha lexicon",
                language=("deu", "German"),
                country="Germany",
                keywords=["lexicon"],
                collection="Collection A",
            ),
            _record(
                "bundle-c",
                "Gamma word list",
                language=("aka", "Akan"),
                country="Germany",
                keywords=["lexicon"],
                collection="Collection C",
            ),
        ],
        definitions=BUNDLE_FACET_DEFINITIONS,
    )


def _params(query: str) -> QueryDict:
    return QueryDict(query)


def test_public_search_query_uses_or_within_facets_and_and_between_facets():
    result = _engine().search(
        _params("language=aka&language=deu&country=Germany"),
    )

    assert [record.identifier for record in result.records] == [
        "bundle-a",
        "bundle-c",
    ]
    assert result.total_count == EXPECTED_FILTERED_RECORDS
    assert [(item["facet_name"], item["value"]) for item in result.active_filters] == [
        ("language", "aka"),
        ("language", "deu"),
        ("country", "Germany"),
    ]


def test_public_search_query_supports_prefix_text_and_field_scoping():
    default_result = _engine().search(_params("q=narr"))
    scoped_result = _engine().search(_params("q=Ghan&search_in=location"))
    no_match = _engine().search(_params("q=Ghan&search_in=title"))

    assert [record.identifier for record in default_result.records] == ["bundle-b"]
    assert [record.identifier for record in scoped_result.records] == ["bundle-b"]
    assert no_match.records == []


def test_public_search_query_preserves_sort_order_and_exact_facet_counts():
    result = _engine().search(_params("sort=language&order=desc"))

    assert [record.identifier for record in result.records] == [
        "bundle-a",
        "bundle-b",
        "bundle-c",
    ]
    language = next(facet for facet in result.facets if facet.name == "language")
    assert {value.value: value.count for value in language.values} == {
        "aka": 2,
        "deu": 1,
    }


def test_public_search_query_rejects_excessive_selection_count():
    values = "&".join(f"language=value-{index}" for index in range(5))

    with pytest.raises(FacetSelectionLimitError, match="language"):
        _engine().search(_params(values))
