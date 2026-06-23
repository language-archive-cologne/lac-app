"""Tests for the faceted search service and view."""

from __future__ import annotations

from datetime import date
import re

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import CharField, OuterRef, Subquery
from django.db.models.functions import Cast
from django.http import QueryDict
from django.test import RequestFactory
from django.urls import reverse

from lacos.blam.models import Bundle, Collection
from lacos.blam.models.base_indentifiers import AccessTypeChoices, IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
)

from lacos.explorer.facets import FACET_CACHE_KEY
from lacos.explorer.facets import FACET_MAX_SELECTED_VALUES
from lacos.explorer.facets import FACET_MAX_TOTAL_SELECTED_VALUES
from lacos.explorer.facets import FacetService
from lacos.explorer.models import BundleFileTypeFacet
from lacos.explorer.search_indexing import update_collection_search_vector
from lacos.storage.models.acl_permissions import ACLPermissions


def _create_collection(
    identifier: str,
    title: str,
    *,
    languages: list[tuple[str, str]] | None = None,
    country: str | None = None,
    region: str | None = None,
    description: str | None = None,
) -> Collection:
    """Helper to create a collection with related metadata."""
    collection = Collection.objects.create(identifier=identifier)
    if country is None:
        country = ""
    location = CollectionLocation.objects.create(
        country_facet=country,
        country_name=country,
        country_code=country[:2].upper() if country else "",
        region_facet=region or "",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"CID-{identifier}",
        id_type=IdentifierTypeChoices.DOI,
        display_title=title,
        description=description or f"Description for {title}",
        location=location,
        version="1.0",
    )
    if languages:
        for name, iso_code in languages:
            lang = CollectionObjectLanguage.objects.create(
                display_name=name,
                name=name,
                iso_639_3_code=iso_code,
                glottolog_code=f"{iso_code}1234",
            )
            general_info.object_languages.add(lang)
    return collection


def _collection_qs():
    """Return a Collection queryset annotated with acl_access_level (mirrors the view)."""
    collection_ct = ContentType.objects.get_for_model(Collection)
    return Collection.objects.annotate(
        acl_access_level=Subquery(
            ACLPermissions.objects.filter(
                content_type=collection_ct,
                object_id=Cast(OuterRef("pk"), output_field=CharField()),
            ).values("access_level")[:1]
        )
    )


def _make_params(**kwargs) -> QueryDict:
    """Build a QueryDict from keyword arguments (supports lists)."""
    qd = QueryDict(mutable=True)
    for key, value in kwargs.items():
        if isinstance(value, list):
            qd.setlist(key, value)
        else:
            qd[key] = value
    return qd


@pytest.mark.django_db
def test_facet_selection_values_are_capped_per_facet():
    values = [f"lang-{i}" for i in range(FACET_MAX_SELECTED_VALUES + 3)]

    result = FacetService().search(
        _make_params(language=values),
        _collection_qs().none(),
    )

    assert [
        active_filter["value"] for active_filter in result.active_filters
    ] == values[:FACET_MAX_SELECTED_VALUES]


@pytest.mark.django_db
def test_facet_selection_values_are_capped_across_request():
    values = [f"value-{i}" for i in range(FACET_MAX_SELECTED_VALUES + 3)]
    years = [str(2000 + i) for i in range(FACET_MAX_SELECTED_VALUES + 3)]
    params = _make_params(
        keyword=values,
        language=values,
        year=years,
        country=values,
        region=values,
        license=values,
    )

    result = FacetService().search(params, _collection_qs().none())

    active_filters_by_name: dict[str, list[str]] = {}
    for active_filter in result.active_filters:
        active_filters_by_name.setdefault(active_filter["facet_name"], []).append(
            active_filter["value"],
        )

    assert len(result.active_filters) == FACET_MAX_TOTAL_SELECTED_VALUES
    assert all(
        len(active_values) <= FACET_MAX_SELECTED_VALUES
        for active_values in active_filters_by_name.values()
    )


@pytest.mark.django_db
def test_invalid_year_facet_values_are_ignored():
    result = FacetService().search(
        _make_params(year=["not-a-year", "2024"]),
        _collection_qs().none(),
    )

    assert [
        active_filter["value"] for active_filter in result.active_filters
    ] == ["2024"]


@pytest.mark.django_db
def test_no_filters_returns_all_collections():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    result = service.search(_make_params(), _collection_qs())

    assert result.queryset.count() == 2
    assert len(result.active_filters) == 0


@pytest.mark.django_db
def test_single_language_filter():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    result = service.search(_make_params(language=["aka"]), _collection_qs())

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert c1.pk in pks


@pytest.mark.django_db
def test_keyword_facet_values_and_filtering():
    c1 = _create_collection("C1", "Alpha")
    c2 = _create_collection("C2", "Beta")

    gi1 = c1.general_info.first()
    gi2 = c2.general_info.first()
    gi1.keywords.add(CollectionKeyword.objects.create(value="phonology"))
    gi2.keywords.add(CollectionKeyword.objects.create(value="lexicon"))

    service = FacetService()
    result = service.search(_make_params(keyword=["phonology"]), _collection_qs())

    assert result.queryset.count() == 1
    pks = set(result.queryset.values_list("pk", flat=True))
    assert pks == {c1.pk}

    keyword_facet = next(f for f in result.facets if f.name == "keyword")
    values = {fv.value for fv in keyword_facet.values}
    assert "phonology" in values
    assert "lexicon" in values


@pytest.mark.django_db
def test_multi_language_filter_or_logic():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    c2 = _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")
    _create_collection("C3", "Gamma", languages=[("Bambara", "bam")], country="Mali")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka", "sef"]), _collection_qs()
    )

    assert result.queryset.count() == 2
    pks = set(result.queryset.values_list("pk", flat=True))
    assert pks == {c1.pk, c2.pk}


@pytest.mark.django_db
def test_country_filter():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    c2 = _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    result = service.search(
        _make_params(country=["Germany"]), _collection_qs()
    )

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert c2.pk in pks


@pytest.mark.django_db
def test_file_type_filter_matches_collections_with_linked_bundle():
    c1 = _create_collection("C1", "ELAN Collection")
    _create_collection("C2", "PDF Collection")
    bundle = Bundle.objects.create(identifier="B1")
    BundleStructuralInfo.objects.create(
        bundle=bundle,
        is_member_of_collection=c1,
    )
    BundleFileTypeFacet.objects.create(
        bundle=bundle,
        collection=c1,
        file_type="eaf",
    )

    service = FacetService()
    result = service.search(_make_params(file_type=["eaf"]), _collection_qs())

    assert result.queryset.count() == 1
    assert list(result.queryset.values_list("pk", flat=True)) == [c1.pk]
    file_type_facet = next(f for f in result.facets if f.name == "file_type")
    assert file_type_facet.label == "File format"
    assert file_type_facet.values[0].label == "ELAN"


@pytest.mark.django_db
def test_cross_facet_and_logic():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Akan", "aka")], country="Germany")
    _create_collection("C3", "Gamma", languages=[("Senufo", "sef")], country="Ghana")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka"], country=["Ghana"]), _collection_qs()
    )

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert c1.pk in pks


@pytest.mark.django_db
def test_cross_facet_counts_exclude_own_facet():
    """When a language is selected, language facet counts should NOT be filtered by language selection."""
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Ghana")
    _create_collection("C3", "Gamma", languages=[("Bambara", "bam")], country="Germany")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka"]), _collection_qs()
    )

    # Language facet should count against base_qs (no language filter applied)
    # so all 3 languages should appear with count > 0
    lang_facet = next(f for f in result.facets if f.name == "language")
    lang_values = {fv.value: fv.count for fv in lang_facet.values}
    assert lang_values["aka"] >= 1
    assert lang_values["sef"] >= 1
    assert lang_values["bam"] >= 1

    # Country facet should be filtered by language=aka (only Ghana has Akan)
    country_facet = next(f for f in result.facets if f.name == "country")
    country_values = {fv.value: fv.count for fv in country_facet.values}
    assert country_values.get("Ghana", 0) == 1
    assert country_values.get("Germany", 0) == 0 or "Germany" not in country_values


@pytest.mark.django_db
def test_selected_value_with_zero_count_preserved():
    """Selected values should remain visible even if cross-facet count is 0."""
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    # Select language=aka AND country=Germany -> 0 results for the combo,
    # but both values should still appear so user can deselect
    result = service.search(
        _make_params(language=["aka"], country=["Germany"]), _collection_qs()
    )

    lang_facet = next(f for f in result.facets if f.name == "language")
    aka_fv = next((fv for fv in lang_facet.values if fv.value == "aka"), None)
    assert aka_fv is not None
    assert aka_fv.selected is True


@pytest.mark.django_db
def test_empty_database():
    service = FacetService()
    result = service.search(_make_params(), _collection_qs())

    assert result.queryset.count() == 0
    for facet in result.facets:
        assert len(facet.values) == 0


@pytest.mark.django_db
def test_null_facet_values_excluded():
    """Collections with empty country_facet should not appear in country facet."""
    # Create collection with a location that has empty country_facet
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Ghana")

    service = FacetService()
    result = service.search(_make_params(), _collection_qs())

    country_facet = next(f for f in result.facets if f.name == "country")
    values = [fv.value for fv in country_facet.values]
    assert "" not in values
    assert None not in values
    assert "Ghana" in values


@pytest.mark.django_db
def test_duplicate_params_deduplicated():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")

    qd = QueryDict(mutable=True)
    qd.setlist("language", ["aka", "aka", " aka "])

    service = FacetService()
    result = service.search(qd, _collection_qs())

    assert result.queryset.count() == 1
    # Only one chip should be generated despite duplicates
    lang_chips = [f for f in result.active_filters if f["facet_name"] == "language"]
    assert len(lang_chips) == 1


@pytest.mark.django_db
def test_active_filter_chips_generated():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka"], country=["Ghana"]), _collection_qs()
    )

    assert len(result.active_filters) == 2
    names = {f["facet_name"] for f in result.active_filters}
    assert names == {"language", "country"}
    # Check labels are resolved (not just codes)
    lang_chip = next(f for f in result.active_filters if f["facet_name"] == "language")
    assert lang_chip["label"] == "Akan"


@pytest.mark.django_db
def test_access_level_facet_shows_human_readable_labels():
    """Access level facet should display human-readable labels from ACL, not BLAM metadata."""
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    collection_ct = ContentType.objects.get_for_model(Collection)
    ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(c1.pk),
        access_level="public",
    )

    service = FacetService()
    result = service.search(_make_params(), _collection_qs())

    access_facet = next(f for f in result.facets if f.name == "access")
    public_fv = next((fv for fv in access_facet.values if fv.value == "public"), None)
    assert public_fv is not None
    assert public_fv.label == "Public"


@pytest.mark.django_db
def test_text_search_combined_with_facets(client):
    c1 = _create_collection("C1", "Senufo Archive", languages=[("Senufo", "sef")], country="Mali")
    c2 = _create_collection("C2", "Akan Archive", languages=[("Akan", "aka")], country="Ghana")
    update_collection_search_vector(c1)
    update_collection_search_vector(c2)

    response = client.get("/search/", {"q": "Senufo", "country": "Mali"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_text_search_highlights_literal_query_in_description(client):
    c1 = _create_collection(
        "C1",
        "Language Variety Archive",
        country="Mali",
        description="Documentation of language variety in Latin America and the Caribbean.",
    )
    update_collection_search_vector(c1)

    response = client.get("/search/", {"q": "var"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>var</mark>" in page


@pytest.mark.django_db
def test_text_search_is_case_insensitive(client):
    c1 = _create_collection(
        "C1",
        "Case Search Archive",
        country="Mali",
        description="Description text for case-insensitive lookup.",
    )
    update_collection_search_vector(c1)

    lowercase_response = client.get("/search/", {"q": "description"})
    uppercase_response = client.get("/search/", {"q": "Description"})

    assert lowercase_response.status_code == 200
    assert uppercase_response.status_code == 200
    assert [c.identifier for c in lowercase_response.context["collections"]] == ["C1"]
    assert [c.identifier for c in uppercase_response.context["collections"]] == ["C1"]


@pytest.mark.django_db
def test_text_search_highlights_literal_query_in_title(client):
    c1 = _create_collection(
        "C1",
        "Etymological Archive",
        country="Mali",
        description="Reference material.",
    )
    update_collection_search_vector(c1)

    response = client.get("/search/", {"q": "ety"})
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "<mark>Ety</mark>mological" in page
    assert "Matched in" in page
    assert "title" in page
    assert re.search(
        r"C1</div>\s*<div class=\"mt-2 flex flex-wrap items-center gap-1\.5 text-xs matched-in-row\">",
        page,
    )


@pytest.mark.django_db
def test_invalid_sort_param_uses_default(client):
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")

    response = client.get("/search/", {"sort": "INVALID"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_page_reset_on_filter_change():
    """Template tags should reset page param when filters change."""
    factory = RequestFactory()
    request = factory.get("/search/", {"language": "aka", "page": "3"})

    from django.template import Context, Template

    template = Template(
        "{% load explorer_extras %}{% facet_toggle_url 'country' 'Ghana' as url %}{{ url }}"
    )
    context = Context({"request": request})
    rendered = template.render(context)

    assert "page=" not in rendered
    assert "country=Ghana" in rendered
    assert "language=aka" in rendered


@pytest.mark.django_db
def test_faceted_search_page_loads(client):
    """The /search/ page should render without errors."""
    response = client.get("/search/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_faceted_search_paginates_twenty_five_results(client):
    for index in range(26):
        _create_collection(f"C{index:02d}", f"Collection {index:02d}")

    response = client.get("/search/")

    assert response.status_code == 200
    assert len(response.context["collections"]) == 25
    assert response.context["paginator"].per_page == 25
    assert response.context["is_paginated"] is True


@pytest.mark.django_db
def test_faceted_search_renders_one_result_row_per_collection(client):
    collection = _create_collection("C1", "Alpha")

    response = client.get("/search/")

    assert response.status_code == 200
    detail_path = reverse(
        "explorer:collection_detail_by_handle",
        kwargs={"handle": collection.handle_path},
    )
    assert response.content.decode("utf-8").count(detail_path) == 1


@pytest.mark.django_db
def test_faceted_search_uses_csp_safe_facet_filter(client):
    response = client.get("/search/")
    assert response.status_code == 200
    page = response.content.decode("utf-8")

    assert 'src="/static/js/src/facet-filter.js"' in page
    assert "data-facet-filter-input" in page
    assert "data-facet-filter-scope" in page
    assert "hx-on:input" not in page


@pytest.mark.django_db
def test_scope_switch_button_does_not_become_default_search_submitter(client):
    response = client.get("/search/")
    assert response.status_code == 200
    page = response.content.decode("utf-8")

    assert 'type="button" data-search-scope-submit' in page
    assert 'form="faceted-search-form"' not in page


@pytest.mark.django_db
def test_search_page_uses_unified_terminology(client):
    response = client.get("/search/")
    assert response.status_code == 200
    page = response.content.decode("utf-8")

    assert "Archive Explorer" in page
    assert "Search in" in page
    assert ">Mode<" not in page
    assert ">Faceted<" not in page
    assert ">Fields<" not in page


@pytest.mark.django_db
def test_htmx_returns_partial(client):
    """HTMX requests should return partial HTML."""
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")

    response = client.get(
        "/search/", {"language": "aka"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "facet-sidebar-inner" in content
    assert "active-filters-wrapper" in content


@pytest.mark.django_db
def test_faceted_search_template_resets_loading_on_history_restore(client):
    """Back/forward navigation should clear stale loading lock state."""
    response = client.get("/search/")
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert '"refreshOnHistoryMiss":true' in page
    assert "htmx:historyRestore" in page
    assert "htmx:historyCacheMissLoad" in page
    assert "htmx:historyCacheMissLoadError" in page
    assert "window.addEventListener('pageshow'" in page
    assert "setLoading(false)" in page


# ---------------------------------------------------------------------------
# Filtered-path facet caching
# ---------------------------------------------------------------------------


@pytest.fixture
def compute_counter(monkeypatch):
    """Count how many times facets are actually computed (vs served from cache)."""
    calls = {"n": 0}
    original = FacetService._compute_facets

    def counting(self, base_qs, selections):
        calls["n"] += 1
        return original(self, base_qs, selections)

    monkeypatch.setattr(FacetService, "_compute_facets", counting)
    return calls


def _collection_with_keywords(identifier: str, *keywords: str):
    collection = _create_collection(identifier, identifier)
    general_info = collection.general_info.first()
    for value in keywords:
        general_info.keywords.add(CollectionKeyword.objects.create(value=value))
    return collection


@pytest.fixture
def explorer_cache_invalidations(monkeypatch):
    """Count signal-driven explorer cache invalidations."""
    from lacos.blam import signals as blam_signals

    calls = {"n": 0}

    def counting_invalidation():
        calls["n"] += 1

    monkeypatch.setattr(
        blam_signals,
        "_invalidate_explorer_caches",
        counting_invalidation,
    )
    return calls


@pytest.mark.django_db
def test_filtered_facets_are_served_from_cache(compute_counter):
    cache.clear()
    _collection_with_keywords("C1", "phonology")
    service = FacetService()

    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )

    assert compute_counter["n"] == 1


@pytest.mark.django_db
def test_filtered_facet_cache_key_is_selection_order_independent(compute_counter):
    cache.clear()
    _collection_with_keywords("C1", "aa", "bb")
    service = FacetService()

    service.search(
        _make_params(keyword=["aa", "bb"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    service.search(
        _make_params(keyword=["bb", "aa"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )

    assert compute_counter["n"] == 1


@pytest.mark.django_db
def test_invalidate_cache_busts_filtered_facet_cache(compute_counter):
    cache.clear()
    _collection_with_keywords("C1", "phonology")
    service = FacetService()

    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    assert compute_counter["n"] == 1

    FacetService.invalidate_cache()
    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    assert compute_counter["n"] == 2


@pytest.mark.django_db
def test_distinct_filtered_selections_are_cached_separately(compute_counter):
    cache.clear()
    _collection_with_keywords("C1", "phonology", "lexicon")
    service = FacetService()

    service.search(
        _make_params(keyword=["phonology"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )
    service.search(
        _make_params(keyword=["lexicon"]), _collection_qs(), cache_key=FACET_CACHE_KEY
    )

    assert compute_counter["n"] == 2


@pytest.mark.django_db
def test_collection_keyword_m2m_change_invalidates_facet_cache(
    explorer_cache_invalidations,
):
    collection = _create_collection("C1", "Alpha")
    general_info = collection.general_info.first()
    keyword = CollectionKeyword.objects.create(value="phonology")
    explorer_cache_invalidations["n"] = 0

    general_info.keywords.add(keyword)

    assert explorer_cache_invalidations["n"] == 1


@pytest.mark.django_db
def test_collection_language_m2m_change_invalidates_facet_cache(
    explorer_cache_invalidations,
):
    collection = _create_collection("C1", "Alpha")
    general_info = collection.general_info.first()
    language = CollectionObjectLanguage.objects.create(
        display_name="Akan",
        name="Akan",
        iso_639_3_code="aka",
        glottolog_code="akan1250",
    )
    explorer_cache_invalidations["n"] = 0

    general_info.object_languages.add(language)

    assert explorer_cache_invalidations["n"] == 1


@pytest.mark.django_db
def test_collection_license_m2m_change_invalidates_facet_cache(
    explorer_cache_invalidations,
):
    collection = _create_collection("C1", "Alpha")
    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date.today(),
    )
    license_obj = CollectionLicense.objects.create(
        license_name="CC BY 4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        access=AccessTypeChoices.OPEN,
    )
    explorer_cache_invalidations["n"] = 0

    admin_info.licenses.add(license_obj)

    assert explorer_cache_invalidations["n"] == 1


@pytest.mark.django_db
def test_collection_publication_info_change_invalidates_facet_cache(
    explorer_cache_invalidations,
):
    collection = _create_collection("C1", "Alpha")
    explorer_cache_invalidations["n"] = 0

    publication_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="LAC",
    )
    assert explorer_cache_invalidations["n"] == 1

    publication_info.delete()
    assert explorer_cache_invalidations["n"] == 2


@pytest.mark.django_db
def test_acl_permission_change_invalidates_facet_cache(explorer_cache_invalidations):
    collection = _create_collection("C1", "Alpha")
    collection_ct = ContentType.objects.get_for_model(Collection)
    explorer_cache_invalidations["n"] = 0

    permission = ACLPermissions.objects.create(
        content_type=collection_ct,
        object_id=str(collection.pk),
        access_level="public",
    )
    assert explorer_cache_invalidations["n"] == 1

    permission.delete()
    assert explorer_cache_invalidations["n"] == 2
