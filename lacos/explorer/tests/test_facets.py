"""Tests for the faceted search service and view."""

from __future__ import annotations

import pytest
from django.http import QueryDict
from django.test import RequestFactory

from lacos.blam.models import Collection
from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
)
from lacos.explorer.facets import FacetService


def _create_collection(
    identifier: str,
    title: str,
    *,
    languages: list[tuple[str, str]] | None = None,
    country: str | None = None,
    region: str | None = None,
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
        description=f"Description for {title}",
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
def test_no_filters_returns_all_collections():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    result = service.search(_make_params(), Collection.objects.all())

    assert result.queryset.count() == 2
    assert len(result.active_filters) == 0


@pytest.mark.django_db
def test_single_language_filter():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")

    service = FacetService()
    result = service.search(_make_params(language=["aka"]), Collection.objects.all())

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert c1.pk in pks


@pytest.mark.django_db
def test_multi_language_filter_or_logic():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    c2 = _create_collection("C2", "Beta", languages=[("Senufo", "sef")], country="Germany")
    _create_collection("C3", "Gamma", languages=[("Bambara", "bam")], country="Mali")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka", "sef"]), Collection.objects.all()
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
        _make_params(country=["Germany"]), Collection.objects.all()
    )

    assert result.queryset.count() == 1
    pks = list(result.queryset.values_list("pk", flat=True))
    assert c2.pk in pks


@pytest.mark.django_db
def test_cross_facet_and_logic():
    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    _create_collection("C2", "Beta", languages=[("Akan", "aka")], country="Germany")
    _create_collection("C3", "Gamma", languages=[("Senufo", "sef")], country="Ghana")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka"], country=["Ghana"]), Collection.objects.all()
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
        _make_params(language=["aka"]), Collection.objects.all()
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
        _make_params(language=["aka"], country=["Germany"]), Collection.objects.all()
    )

    lang_facet = next(f for f in result.facets if f.name == "language")
    aka_fv = next((fv for fv in lang_facet.values if fv.value == "aka"), None)
    assert aka_fv is not None
    assert aka_fv.selected is True


@pytest.mark.django_db
def test_empty_database():
    service = FacetService()
    result = service.search(_make_params(), Collection.objects.all())

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
    result = service.search(_make_params(), Collection.objects.all())

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
    result = service.search(qd, Collection.objects.all())

    assert result.queryset.count() == 1
    # Only one chip should be generated despite duplicates
    lang_chips = [f for f in result.active_filters if f["facet_name"] == "language"]
    assert len(lang_chips) == 1


@pytest.mark.django_db
def test_active_filter_chips_generated():
    _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")

    service = FacetService()
    result = service.search(
        _make_params(language=["aka"], country=["Ghana"]), Collection.objects.all()
    )

    assert len(result.active_filters) == 2
    names = {f["facet_name"] for f in result.active_filters}
    assert names == {"language", "country"}
    # Check labels are resolved (not just codes)
    lang_chip = next(f for f in result.active_filters if f["facet_name"] == "language")
    assert lang_chip["label"] == "Akan"


@pytest.mark.django_db
def test_access_level_facet_shows_human_readable_labels():
    """Access level facet should display human-readable labels, not raw DB values."""
    from lacos.blam.models.collection.collection_administrative_info import (
        CollectionAdministrativeInfo,
    )

    c1 = _create_collection("C1", "Alpha", languages=[("Akan", "aka")], country="Ghana")
    CollectionAdministrativeInfo.objects.create(
        collection=c1,
        access_level="public",
        availability_date="2024-01-01",
    )

    service = FacetService()
    result = service.search(_make_params(), Collection.objects.all())

    access_facet = next(f for f in result.facets if f.name == "access")
    public_fv = next((fv for fv in access_facet.values if fv.value == "public"), None)
    assert public_fv is not None
    assert public_fv.label == "Public"


@pytest.mark.django_db
def test_text_search_combined_with_facets(client):
    _create_collection("C1", "Senufo Archive", languages=[("Senufo", "sef")], country="Mali")
    _create_collection("C2", "Akan Archive", languages=[("Akan", "aka")], country="Ghana")

    response = client.get("/search/", {"q": "Senufo", "country": "Mali"})
    assert response.status_code == 200


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
