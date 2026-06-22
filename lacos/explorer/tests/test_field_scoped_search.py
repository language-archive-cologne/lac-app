"""Tests for field-scoped full-text search used by the 'Search in' selector."""

from __future__ import annotations

import pytest
from django.urls import reverse

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
def test_non_searchable_field_term_returns_no_results():
    _collection("C1", "Anything")
    base = Collection.objects.all()

    out = apply_field_scoped_search(base, "a", ["title"], COLLECTION_FIELD_DEFINITIONS)

    assert list(out) == []


@pytest.mark.django_db
def test_no_resolvable_fields_returns_qs_unchanged():
    _collection("C1", "Anything")
    base = Collection.objects.all()
    out = apply_field_scoped_search(base, "Anything", ["nonexistent"], COLLECTION_FIELD_DEFINITIONS)
    assert list(out) == list(base)


@pytest.mark.django_db
def test_search_in_scopes_results(client):
    _collection("C1", "Rock Art Interviews", keyword="ritual")
    url = reverse("faceted_search")
    r_title = client.get(url, {"q": "ritual", "search_in": ["title"]})
    assert r_title.status_code == 200
    assert r_title.context["total_count"] == 0
    r_kw = client.get(url, {"q": "ritual", "search_in": ["keyword"]})
    assert r_kw.context["total_count"] == 1


@pytest.mark.django_db
def test_no_search_in_uses_global_search(client):
    _collection("C1", "Rock Art Interviews", keyword="ritual")
    r = client.get(reverse("faceted_search"), {"q": "ritual"})
    assert r.status_code == 200
    assert r.context["total_count"] == 1


@pytest.mark.django_db
def test_field_definitions_in_context(client):
    r = client.get(reverse("faceted_search"))
    assert r.context["field_definitions"] is not None
    assert r.context["active_search_in"] == []


@pytest.mark.django_db
def test_search_in_selection_renders_labeled_chips(client):
    _collection("C1", "Rock Art Interviews", keyword="ritual")
    r = client.get(
        reverse("faceted_search"), {"q": "ritual", "search_in": ["title", "keyword"]}
    )
    assert r.status_code == 200
    page = r.content.decode("utf-8")
    assert page.count("Search in:") == 2
    # removing one field keeps the other selected
    assert "search_in=keyword" in page
    assert "search_in=title" in page


@pytest.mark.django_db
def test_no_search_in_renders_no_chips(client):
    r = client.get(reverse("faceted_search"), {"q": "ritual"})
    assert "Search in:" not in r.content.decode("utf-8")


@pytest.mark.django_db
def test_bundle_search_in_selection_renders_labeled_chips(client):
    r = client.get(
        reverse("bundle_faceted_search"), {"q": "ritual", "search_in": ["title"]}
    )
    assert r.status_code == 200
    page = r.content.decode("utf-8")
    assert page.count("Search in:") == 1


def test_clear_all_filters_drops_search_in():
    from django.test import RequestFactory

    from lacos.explorer.templatetags.explorer_extras import clear_all_filters_url

    request = RequestFactory().get(
        "/search/",
        {"q": "x", "search_in": ["title"], "language": "Yuracare", "file_type": "wav"},
    )
    url = clear_all_filters_url({"request": request})
    assert "search_in" not in url
    assert "file_type" not in url
