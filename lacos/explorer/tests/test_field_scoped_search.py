"""Tests for field-scoped full-text search used by the 'Search in' selector."""

from __future__ import annotations

import pytest

from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
)
from lacos.explorer.advanced_search import (
    COLLECTION_FIELD_DEFINITIONS,
    apply_field_scoped_search,
)
from lacos.explorer.search_indexing import update_collection_search_vector


def _collection(identifier: str, title: str, *, keyword: str | None = None) -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="Test Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    gi = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"CID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=f"Description for {title}",
        location=location,
    )
    if keyword:
        gi.keywords.add(CollectionKeyword.objects.create(value=keyword))
    update_collection_search_vector(collection)
    return collection


@pytest.mark.django_db
def test_matches_term_within_selected_field():
    target = _collection("C1", "Rock Art Interviews")
    _collection("C2", "Unrelated Songs")
    qs = apply_field_scoped_search(
        Collection.objects.all(), "Rock", ["title"], COLLECTION_FIELD_DEFINITIONS
    )
    assert list(qs) == [target]


@pytest.mark.django_db
def test_does_not_match_when_field_not_selected():
    _collection("C1", "Rock Art Interviews", keyword="ritual")
    qs = apply_field_scoped_search(
        Collection.objects.all(), "Rock", ["keyword"], COLLECTION_FIELD_DEFINITIONS
    )
    assert list(qs) == []


@pytest.mark.django_db
def test_multi_field_is_or_combined():
    a = _collection("C1", "Rock Art", keyword="ritual")
    b = _collection("C2", "Songs", keyword="Rock carvings")
    _collection("C3", "Nothing")
    qs = apply_field_scoped_search(
        Collection.objects.all(), "Rock", ["title", "keyword"], COLLECTION_FIELD_DEFINITIONS
    )
    assert set(qs) == {a, b}


@pytest.mark.django_db
def test_empty_term_returns_qs_unchanged():
    _collection("C1", "Anything")
    base = Collection.objects.all()
    assert list(apply_field_scoped_search(base, "   ", ["title"], COLLECTION_FIELD_DEFINITIONS)) == list(base)


@pytest.mark.django_db
def test_no_resolvable_fields_returns_qs_unchanged():
    _collection("C1", "Anything")
    base = Collection.objects.all()
    out = apply_field_scoped_search(base, "Anything", ["nonexistent"], COLLECTION_FIELD_DEFINITIONS)
    assert list(out) == list(base)
