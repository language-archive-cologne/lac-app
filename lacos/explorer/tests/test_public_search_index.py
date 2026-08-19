"""Public search index generation and storage coverage."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.http import QueryDict

from lacos.blam.models import Bundle
from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS
from lacos.explorer.public_search.builder import build_public_search_index
from lacos.explorer.public_search.query import PublicSearchQueryEngine
from lacos.explorer.public_search.store import PublicSearchIndexError
from lacos.explorer.public_search.store import load_public_search_index
from lacos.explorer.public_search.store import write_public_search_index
from lacos.explorer.search_indexing import update_bundle_search_vector
from lacos.explorer.tests.test_bundle_facets import _create_bundle
from lacos.explorer.tests.test_bundle_facets import _create_collection
from lacos.explorer.text_search import apply_text_search

SHA256_HEX_LENGTH = 64


class _RestrictedExposurePolicy:
    """Test policy that exposes only identifiers without a private prefix."""

    @staticmethod
    def anonymous_user():
        return None

    @staticmethod
    def filter_collection_queryset(user, queryset, *, channel):
        del user, channel
        return queryset.exclude(identifier__startswith="private")

    @staticmethod
    def filter_bundle_queryset(user, queryset, *, channel):
        del user, channel
        return queryset.exclude(identifier__startswith="private")


@pytest.mark.django_db
def test_public_search_index_is_deterministic_and_contains_search_metadata():
    collection = _create_collection("hdl:test/collection", "Test Collection")
    _create_bundle(
        "hdl:test/bundle",
        "Recorded Stories",
        collection,
        languages=[("Akan", "aka")],
        country="Ghana",
        region="West Africa",
        description="Public language documentation",
    )

    first = build_public_search_index()
    second = build_public_search_index()

    assert first == second
    assert first["schema_version"] == 1
    assert len(first["version"]) == SHA256_HEX_LENGTH
    assert [record["identifier"] for record in first["collections"]] == [
        "hdl:test/collection",
    ]
    bundle = first["bundles"][0]
    assert bundle["identifier"] == "hdl:test/bundle"
    assert bundle["title"] == "Recorded Stories"
    assert bundle["languages"] == [
        {
            "code": "aka",
            "name": "Akan",
            "display_name": "Akan",
            "alternative_names": [],
        },
    ]
    assert bundle["facets"]["country"] == ["Ghana"]
    assert bundle["facets"]["region"] == ["West Africa"]
    assert bundle["collection"]["identifier"] == "hdl:test/collection"


@pytest.mark.django_db
def test_public_search_index_applies_anonymous_exposure_policy():
    visible = _create_collection("public-collection", "Visible")
    hidden = _create_collection("private-collection", "Hidden")
    _create_bundle("public-bundle", "Visible bundle", visible)
    _create_bundle("private-bundle", "Hidden bundle", hidden)

    index = build_public_search_index(policy=_RestrictedExposurePolicy())

    assert [record["identifier"] for record in index["collections"]] == [
        "public-collection",
    ]
    assert [record["identifier"] for record in index["bundles"]] == [
        "public-bundle",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("query", ["stories", "Akan", "Ghana"])
def test_public_index_text_matches_postgres_vector_for_shared_fields(query):
    collection = _create_collection("parity-collection", "Parity Collection")
    story = _create_bundle(
        "story-bundle",
        "A language story",
        collection,
        languages=[("Akan", "aka")],
        country="Ghana",
    )
    other = _create_bundle(
        "other-bundle",
        "A lexicon",
        collection,
        languages=[("German", "deu")],
        country="Germany",
    )
    update_bundle_search_vector(story)
    update_bundle_search_vector(other)
    index = build_public_search_index()

    database_ids = set(
        apply_text_search(Bundle.objects.all(), query).values_list(
            "identifier",
            flat=True,
        ),
    )
    public_result = PublicSearchQueryEngine(
        records=index["bundles"],
        definitions=BUNDLE_FACET_DEFINITIONS,
        version=index["version"],
    ).search(QueryDict(f"q={query}"))

    assert {record.identifier for record in public_result.records} == database_ids


@pytest.mark.django_db
def test_management_command_writes_loadable_index(tmp_path):
    collection = _create_collection("collection", "Collection")
    _create_bundle("bundle", "Bundle", collection)
    target = tmp_path / "public-search.json"
    stdout = StringIO()

    call_command("build_public_search_index", output=target, stdout=stdout)

    loaded = load_public_search_index(target)
    assert loaded["collections"][0]["identifier"] == "collection"
    assert loaded["bundles"][0]["identifier"] == "bundle"
    assert loaded["version"] in stdout.getvalue()


def test_public_search_index_store_rejects_corrupt_content(tmp_path):
    target = tmp_path / "public-search.json"
    target.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "not-the-content-hash",
                "collections": [],
                "bundles": [],
            },
        ),
    )

    with pytest.raises(PublicSearchIndexError, match="integrity"):
        load_public_search_index(target)


def test_public_search_index_write_is_compact_and_round_trips(tmp_path):
    target = tmp_path / "public-search.json"
    index = {
        "schema_version": 1,
        "version": "",
        "collections": [],
        "bundles": [],
    }

    version = write_public_search_index(target, index)
    loaded = load_public_search_index(target)

    assert loaded["version"] == version
    assert "\n" not in target.read_text()
