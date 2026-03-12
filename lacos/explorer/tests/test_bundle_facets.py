"""Tests for the bundle faceted search service and view."""

from __future__ import annotations

import re

import pytest
from django.http import QueryDict

from lacos.blam.models import Bundle, Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleKeyword,
    BundleLocation,
    BundleObjectLanguage,
)
from lacos.blam.models.bundle.bundle_publication_info import BundlePublicationInfo
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.explorer.facets import BUNDLE_FACET_DEFINITIONS, FacetService
from lacos.explorer.search_indexing import update_bundle_search_vector


def _create_collection(identifier: str, title: str) -> Collection:
    """Helper to create a minimal parent collection."""
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        country_facet="",
        country_name="",
        country_code="",
        region_facet="",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"CID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=f"Description for {title}",
        location=location,
        version="1.0",
    )
    return collection


def _create_bundle(
    identifier: str,
    title: str,
    collection: Collection,
    *,
    languages: list[tuple[str, str]] | None = None,
    country: str | None = None,
    region: str | None = None,
    description: str | None = None,
) -> Bundle:
    """Helper to create a bundle with related metadata."""
    bundle = Bundle.objects.create(identifier=identifier)

    location = BundleLocation.objects.create(
        country_facet=country or "",
        country_name=country or "",
        country_code=(country[:2].upper() if country else ""),
        region_facet=region or "",
    )
    general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"BID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=description or f"Description for {title}",
        location=location,
        version="1.0",
    )
    if languages:
        for name, iso_code in languages:
            lang, _ = BundleObjectLanguage.objects.get_or_create(
                iso_639_3_code=iso_code,
                defaults={
                    "display_name": name,
                    "name": name,
                    "glottolog_code": f"{iso_code}1234",
                },
            )
            general_info.object_languages.add(lang)

    structural_info = BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=collection,
    )
    BundlePublicationInfo.objects.create(
        bundle=bundle,
        publication_year=2024,
        data_provider="Test Provider",
        identifier=f"PUB-{identifier}",
        identifier_type="DOI",
    )

    return bundle


def _make_params(**kwargs) -> QueryDict:
    """Build a QueryDict from keyword arguments (supports lists)."""
    qd = QueryDict(mutable=True)
    for key, value in kwargs.items():
        if isinstance(value, list):
            qd.setlist(key, value)
        else:
            qd[key] = value
    return qd


def _service() -> FacetService:
    return FacetService(definitions=BUNDLE_FACET_DEFINITIONS)


@pytest.mark.django_db
def test_no_filters_returns_all_bundles():
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll, languages=[("Akan", "aka")], country="Ghana")
    _create_bundle("B2", "Beta", coll, languages=[("Senufo", "sef")], country="Germany")

    result = _service().search(_make_params(), Bundle.objects.all())

    assert result.queryset.count() == 2
    assert len(result.active_filters) == 0


@pytest.mark.django_db
def test_single_language_filter():
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Alpha", coll, languages=[("Akan", "aka")])
    _create_bundle("B2", "Beta", coll, languages=[("Senufo", "sef")])

    result = _service().search(_make_params(language=["aka"]), Bundle.objects.all())

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert b1.pk in pks


@pytest.mark.django_db
def test_unknown_topic_filter_is_ignored():
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll)
    _create_bundle("B2", "Beta", coll)

    result = _service().search(
        _make_params(topic=["narrative"]), Bundle.objects.all()
    )

    assert result.queryset.count() == 2
    assert result.active_filters == []


@pytest.mark.django_db
def test_collection_filter():
    coll1 = _create_collection("C1", "Collection One")
    coll2 = _create_collection("C2", "Collection Two")
    b1 = _create_bundle("B1", "Alpha", coll1)
    _create_bundle("B2", "Beta", coll2)

    result = _service().search(
        _make_params(collection=["C1"]), Bundle.objects.all()
    )

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert b1.pk in pks


@pytest.mark.django_db
def test_cross_facet_and_logic():
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle(
        "B1", "Alpha", coll,
        languages=[("Akan", "aka")], country="Ghana",
    )
    _create_bundle(
        "B2", "Beta", coll,
        languages=[("Akan", "aka")], country="Germany",
    )
    _create_bundle(
        "B3", "Gamma", coll,
        languages=[("Senufo", "sef")], country="Ghana",
    )

    result = _service().search(
        _make_params(language=["aka"], country=["Ghana"]), Bundle.objects.all()
    )

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert b1.pk in pks


@pytest.mark.django_db
def test_cross_facet_counts_exclude_own_facet():
    """When a language is selected, language facet counts should NOT be filtered by language selection."""
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll, languages=[("Akan", "aka")], country="Ghana")
    _create_bundle("B2", "Beta", coll, languages=[("Senufo", "sef")], country="Ghana")
    _create_bundle("B3", "Gamma", coll, languages=[("Bambara", "bam")], country="Germany")

    result = _service().search(
        _make_params(language=["aka"]), Bundle.objects.all()
    )

    lang_facet = next(f for f in result.facets if f.name == "language")
    lang_values = {fv.value: fv.count for fv in lang_facet.values}
    assert lang_values["aka"] >= 1
    assert lang_values["sef"] >= 1
    assert lang_values["bam"] >= 1

    country_facet = next(f for f in result.facets if f.name == "country")
    country_values = {fv.value: fv.count for fv in country_facet.values}
    assert country_values.get("Ghana", 0) == 1
    assert country_values.get("Germany", 0) == 0 or "Germany" not in country_values


@pytest.mark.django_db
def test_bundle_facets_do_not_include_removed_topic_dimension():
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll)
    _create_bundle("B2", "Beta", coll)
    _create_bundle("B3", "Gamma", coll)

    result = _service().search(_make_params(), Bundle.objects.all())

    assert all(f.name != "topic" for f in result.facets)


@pytest.mark.django_db
def test_empty_database():
    result = _service().search(_make_params(), Bundle.objects.all())

    assert result.queryset.count() == 0
    for facet in result.facets:
        assert len(facet.values) == 0


@pytest.mark.django_db
def test_collection_facet_shows_display_title():
    """Collection facet should show display titles, not identifiers."""
    coll = _create_collection("C1", "Senufo Language Archive")
    _create_bundle("B1", "Alpha", coll)

    result = _service().search(_make_params(), Bundle.objects.all())

    coll_facet = next(f for f in result.facets if f.name == "collection")
    assert len(coll_facet.values) == 1
    fv = coll_facet.values[0]
    assert fv.value == "C1"
    assert fv.label == "Senufo Language Archive"


@pytest.mark.django_db
def test_active_filter_chips_generated():
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll, languages=[("Akan", "aka")], country="Ghana")

    result = _service().search(
        _make_params(language=["aka"], country=["Ghana"]), Bundle.objects.all()
    )

    assert len(result.active_filters) == 2
    names = {f["facet_name"] for f in result.active_filters}
    assert names == {"language", "country"}
    lang_chip = next(f for f in result.active_filters if f["facet_name"] == "language")
    assert lang_chip["label"] == "Akan"


@pytest.mark.django_db
def test_bundle_faceted_search_page_loads(client):
    """The /search/bundles/ page should render without errors."""
    response = client.get("/search/bundles/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_bundle_htmx_returns_partial(client):
    """HTMX requests should return partial HTML."""
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll, languages=[("Akan", "aka")], country="Ghana")

    response = client.get(
        "/search/bundles/", {"language": "aka"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "facet-sidebar-inner" in content
    assert "active-filters-wrapper" in content


@pytest.mark.django_db
def test_bundle_faceted_search_template_resets_loading_on_history_restore(client):
    """Bundle faceted page should clear stale loading lock on back/forward."""
    response = client.get("/search/bundles/")
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert '"refreshOnHistoryMiss":true' in page
    assert "htmx:historyRestore" in page
    assert "htmx:historyCacheMissLoad" in page
    assert "htmx:historyCacheMissLoadError" in page
    assert "window.addEventListener('pageshow'" in page
    assert "setLoading(false)" in page


@pytest.mark.django_db
def test_text_search_filters_results(client):
    """Verify q= actually removes non-matching bundles from results."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Senufo Stories", coll, languages=[("Senufo", "sef")], country="Mali")
    b2 = _create_bundle("B2", "Akan Archive", coll, languages=[("Akan", "aka")], country="Ghana")
    b3 = _create_bundle("B3", "Bambara Tales", coll, languages=[("Bambara", "bam")], country="Mali")
    for b in (b1, b2, b3):
        update_bundle_search_vector(b)

    response = client.get("/search/bundles/", {"q": "Senufo"})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    identifiers = {b.identifier for b in bundles}
    assert "B1" in identifiers
    assert "B2" not in identifiers
    assert "B3" not in identifiers


@pytest.mark.django_db
def test_text_search_with_facet_filter(client):
    """Verify q= AND language= together narrow results correctly."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle(
        "B1", "Senufo Stories", coll,
        languages=[("Senufo", "sef")], country="Mali",
    )
    b2 = _create_bundle(
        "B2", "Senufo Proverbs", coll,
        languages=[("Akan", "aka")], country="Ghana",
    )
    b3 = _create_bundle(
        "B3", "Akan Archive", coll,
        languages=[("Akan", "aka")], country="Ghana",
    )
    for b in (b1, b2, b3):
        update_bundle_search_vector(b)

    response = client.get("/search/bundles/", {"q": "Senufo", "language": "aka"})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    identifiers = {b.identifier for b in bundles}
    # Only B2 matches both "Senufo" in title AND language=aka
    assert "B2" in identifiers
    assert "B1" not in identifiers  # matches text but wrong language
    assert "B3" not in identifiers  # matches language but not text


@pytest.mark.django_db
def test_text_search_by_description(client):
    """Verify searching by description text works."""
    coll = _create_collection("C1", "Test Collection")
    # _create_bundle sets description to "Description for {title}"
    b1 = _create_bundle("B1", "Alpha Bundle", coll)
    b2 = _create_bundle("B2", "Beta Bundle", coll)
    update_bundle_search_vector(b1)
    update_bundle_search_vector(b2)

    # Search for "Alpha" which appears in B1's description ("Description for Alpha Bundle")
    response = client.get("/search/bundles/", {"q": "Alpha"})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    identifiers = {b.identifier for b in bundles}
    assert "B1" in identifiers
    assert "B2" not in identifiers


@pytest.mark.django_db
def test_text_search_highlights_literal_query_in_description(client):
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle(
        "B1",
        "Language Variety Bundle",
        coll,
        description="Documentation of language variety in Latin America and the Caribbean.",
    )
    update_bundle_search_vector(b1)

    response = client.get("/search/bundles/", {"q": "var"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>var</mark>" in page


@pytest.mark.django_db
def test_text_search_highlights_literal_query_in_title(client):
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle(
        "B1",
        "Etymological Bundle",
        coll,
        description="Reference material.",
    )
    update_bundle_search_vector(b1)

    response = client.get("/search/bundles/", {"q": "ety"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>Ety</mark>mological" in page
    assert "Matched in" in page
    assert "title" in page
    assert re.search(
        r"B1</div>\s*<div class=\"mt-2 flex flex-wrap items-center gap-1\.5 text-xs matched-in-row\">",
        page,
    )


@pytest.mark.django_db
def test_text_search_by_language_name(client):
    """Verify searching by language name works."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Bundle One", coll, languages=[("Senufo", "sef")])
    b2 = _create_bundle("B2", "Bundle Two", coll, languages=[("Akan", "aka")])
    update_bundle_search_vector(b1)
    update_bundle_search_vector(b2)

    response = client.get("/search/bundles/", {"q": "Senufo"})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    identifiers = {b.identifier for b in bundles}
    assert "B1" in identifiers
    assert "B2" not in identifiers


@pytest.mark.django_db
def test_text_search_facets_update(client):
    """Verify facet counts update when text search is active."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Senufo Stories", coll, languages=[("Senufo", "sef")], country="Mali")
    b2 = _create_bundle("B2", "Senufo Proverbs", coll, languages=[("Akan", "aka")], country="Ghana")
    b3 = _create_bundle("B3", "Bambara Tales", coll, languages=[("Bambara", "bam")], country="Mali")
    for b in (b1, b2, b3):
        update_bundle_search_vector(b)

    # Without text search, Mali should have count=2 (B1 + B3)
    response_all = client.get("/search/bundles/")
    country_facet_all = next(f for f in response_all.context["facets"] if f.name == "country")
    mali_all = next((fv for fv in country_facet_all.values if fv.value == "Mali"), None)
    assert mali_all is not None
    assert mali_all.count == 2

    # With text search for "Senufo", only B1 and B2 match, so Mali count=1 (only B1)
    response_search = client.get("/search/bundles/", {"q": "Senufo"})
    country_facet_search = next(f for f in response_search.context["facets"] if f.name == "country")
    mali_search = next((fv for fv in country_facet_search.values if fv.value == "Mali"), None)
    assert mali_search is not None
    assert mali_search.count == 1


@pytest.mark.django_db
def test_text_search_empty_query(client):
    """Verify empty q= returns all results."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Alpha", coll)
    b2 = _create_bundle("B2", "Beta", coll)
    b3 = _create_bundle("B3", "Gamma", coll)
    for b in (b1, b2, b3):
        update_bundle_search_vector(b)

    response = client.get("/search/bundles/", {"q": ""})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    assert len(bundles) == 3


@pytest.mark.django_db
def test_text_search_no_results(client):
    """Verify q= with non-matching term returns empty."""
    coll = _create_collection("C1", "Test Collection")
    b1 = _create_bundle("B1", "Alpha", coll)
    b2 = _create_bundle("B2", "Beta", coll)
    update_bundle_search_vector(b1)
    update_bundle_search_vector(b2)

    response = client.get("/search/bundles/", {"q": "xyznonexistent"})
    assert response.status_code == 200
    bundles = list(response.context["bundles"])
    assert len(bundles) == 0


@pytest.mark.django_db
def test_invalid_sort_param_uses_default(client):
    coll = _create_collection("C1", "Test Collection")
    _create_bundle("B1", "Alpha", coll)

    response = client.get("/search/bundles/", {"sort": "INVALID"})
    assert response.status_code == 200
