import json
from pathlib import Path

import pytest
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionCreator,
    CollectionPublicationInfo,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.explorer.map_utils import get_collection_map_markers


def _build_collection_graph(index: int) -> Collection:
    collection = Collection.objects.create(identifier=f"hdl:test/query-opt-{index}")

    location = CollectionLocation.objects.create(
        geo_location=f"{10 + index}, {20 + index}",
        location_name=f"Location {index}",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/query-opt-general-{index}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=f"Collection {index}",
        description=f"Description {index}",
        version="1.0",
        location=location,
    )
    general_info.keywords.add(CollectionKeyword.objects.create(value=f"kw-{index}"))
    general_info.object_languages.add(
        CollectionObjectLanguage.objects.create(
            display_name=f"Language {index}",
            name=f"Language {index}",
            iso_639_3_code=f"q{index:02d}"[-3:],
            glottolog_code=f"qglot{index:04d}"[:10],
        )
    )

    publication_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2000 + index,
        data_provider="LAC",
    )
    publication_info.creators.add(
        CollectionCreator.objects.create(
            family_name=f"Family{index}",
            given_name=f"Given{index}",
        )
    )

    bundle = Bundle.objects.create(identifier=f"bundle-query-opt-{index}")
    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return collection


def _build_empty_collection(index: int) -> Collection:
    collection = Collection.objects.create(identifier=f"hdl:test/empty-{index}")

    location = CollectionLocation.objects.create(
        geo_location=f"{30 + index}, {40 + index}",
        location_name=f"Empty Location {index}",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"hdl:test/empty-general-{index}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title=f"Empty Collection {index}",
        description=f"Empty description {index}",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(
        CollectionObjectLanguage.objects.create(
            display_name=f"Empty Language {index}",
            name=f"Empty Language {index}",
            iso_639_3_code=f"e{index:02d}"[-3:],
            glottolog_code=f"eglot{index:04d}"[:10],
        )
    )

    return collection


@pytest.mark.django_db
def test_collection_list_full_page_query_budget(client):
    for idx in range(1, 6):
        _build_collection_graph(idx)

    cache.clear()
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("explorer:collection_list"))
        assert response.status_code == 200
        _ = response.content

    assert len(captured) <= 18


@pytest.mark.django_db
def test_collection_list_htmx_sort_query_budget(client):
    for idx in range(1, 6):
        _build_collection_graph(idx)

    cache.clear()
    with CaptureQueriesContext(connection) as captured:
        response = client.get(
            reverse("explorer:collection_list"),
            {"sort": "name", "order": "asc"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="collections-table",
        )
        assert response.status_code == 200
        _ = response.content

    assert len(captured) <= 15


@pytest.mark.django_db
def test_collection_list_htmx_language_shell_query_budget(client):
    for idx in range(1, 6):
        _build_collection_graph(idx)

    cache.clear()
    with CaptureQueriesContext(connection) as captured:
        response = client.get(
            reverse("explorer:collection_list"),
            {"language": "Language 1", "sort": "name", "order": "asc"},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="collection-language-shell",
        )
        assert response.status_code == 200
        _ = response.content

    assert len(captured) <= 15


@pytest.mark.django_db
def test_collection_list_paginates_and_honors_page_parameter(client, settings):
    settings.EXPLORER_COLLECTIONS_PAGE_SIZE = 2
    for idx in range(1, 5):
        _build_collection_graph(idx)

    first_page = client.get(
        reverse("explorer:collection_list"),
        {"sort": "name", "order": "asc"},
    )
    assert first_page.status_code == 200
    assert first_page.context["is_paginated"] is True
    assert first_page.context["page_obj"].number == 1
    assert len(first_page.context["collection_list"]) == 2

    second_page = client.get(
        reverse("explorer:collection_list"),
        {"sort": "name", "order": "asc", "page": 2},
    )
    assert second_page.status_code == 200
    assert second_page.context["page_obj"].number == 2
    assert len(second_page.context["collection_list"]) == 2


@pytest.mark.django_db
def test_collection_list_htmx_pagination_returns_table_partial(client, settings):
    settings.EXPLORER_COLLECTIONS_PAGE_SIZE = 2
    for idx in range(1, 5):
        _build_collection_graph(idx)

    response = client.get(
        reverse("explorer:collection_list"),
        {"sort": "name", "order": "asc", "page": 2},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="collections-table",
    )
    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'id="collections-table"' in page
    assert 'id="collection-language-shell"' not in page
    assert "projection=globe" not in page


@pytest.mark.django_db
def test_collection_list_full_page_uses_globe_style_variant(client):
    _build_collection_graph(1)

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "const GLOBE_STYLE_URL = STYLE_URL + (STYLE_URL.includes('?') ? '&' : '?') + 'projection=globe';" in page
    assert "const GLOBE_DARK_STYLE_URL = DARK_STYLE_URL + (DARK_STYLE_URL.includes('?') ? '&' : '?') + 'projection=globe';" in page
    assert "style: isDark ? GLOBE_DARK_STYLE_URL : GLOBE_STYLE_URL," in page
    assert "setProjection({ type: 'globe' })" not in page


@pytest.mark.django_db
def test_collection_list_full_page_renders_refined_language_index_typography(client):
    _build_collection_graph(1)

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'language-index-card rounded-2xl border shadow-sm h-full flex flex-col' in page
    assert 'language-index-pill inline-flex items-center gap-1 px-2 py-[3px] rounded-md text-xs border transition-colors' in page
    assert 'language-index-pill-iso text-[10.5px] tabular-nums leading-none' in page


def test_language_index_component_styles_define_lighter_neutral_palette():
    css = Path("theme/static_src/css/input.css").read_text()

    assert "--color-base-100: #ffffff;" in css
    assert "--color-base-200: #f2f2f2;" in css
    assert "--color-base-300: #e5e6e6;" in css
    assert "--color-base-content: #1f2937;" in css
    assert ".language-index-card" in css
    assert "background: var(--color-base-100);" in css
    assert "border-color: var(--color-base-300);" in css
    assert ".language-index-pill" in css
    assert "background: #f6f6f6;" in css
    assert "color: var(--color-base-content);" in css


@pytest.mark.django_db
def test_collection_list_excludes_zero_bundle_collections(client):
    empty_collection = _build_empty_collection(1)
    visible_collection = _build_collection_graph(1)

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    rendered_ids = {collection.pk for collection in response.context["collection_list"]}
    assert visible_collection.pk in rendered_ids
    assert empty_collection.pk not in rendered_ids


@pytest.mark.django_db
def test_collection_map_markers_exclude_zero_bundle_collections():
    cache.clear()
    empty_collection = _build_empty_collection(2)
    visible_collection = _build_collection_graph(2)

    markers = json.loads(get_collection_map_markers())
    marker_urls = {marker["url"] for marker in markers}

    assert f"/collections/{visible_collection.pk}/" in marker_urls
    assert f"/collections/{empty_collection.pk}/" not in marker_urls
