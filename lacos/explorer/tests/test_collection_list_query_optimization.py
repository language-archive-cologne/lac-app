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


@pytest.mark.django_db
def test_collection_list_full_page_query_budget(client):
    for idx in range(1, 6):
        _build_collection_graph(idx)

    cache.clear()
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("explorer:collection_list"))
        assert response.status_code == 200
        _ = response.content

    assert len(captured) <= 16


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
