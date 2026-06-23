from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from lacos.explorer.templatetags.explorer_extras import handle_resolver_url, urlize_text
from lacos.explorer.tests.test_collection_list_query_optimization import _build_collection_graph


def test_urlize_text_escapes_html_before_linkifying():
    rendered = str(urlize_text('<img src=x onerror=alert(1)> https://example.com'))

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert 'href="https://example.com"' in rendered


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "hdl:11341/0000-0000-0000-3235",
            "https://hdl.handle.net/11341/0000-0000-0000-3235",
        ),
        (
            "https://hdl.handle.net/11341/0000-0000-0000-3235",
            "https://hdl.handle.net/11341/0000-0000-0000-3235",
        ),
        ("doi:10.1234/example", "doi:10.1234/example"),
    ],
)
def test_handle_resolver_url_filter_normalizes_hdl_values(value, expected):
    assert handle_resolver_url(value) == expected


@pytest.mark.django_db
def test_collection_list_escapes_map_marker_json_titles(client):
    collection = _build_collection_graph(91)
    general_info = collection.general_info.first()
    general_info.display_title = "</script><script>alert(1)</script>"
    general_info.save(update_fields=["display_title"])

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "collections-markers" in page
    assert "</script><script>alert(1)</script>" not in page


@pytest.mark.django_db
def test_collection_list_map_triggers_use_delegated_modal_js(client):
    collection = _build_collection_graph(92)
    location = collection.general_info.first().location
    location.region_facet = "Region"
    location.country_facet = "Country"
    location.save(update_fields=["region_facet", "country_facet"])

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert 'src="/static/js/src/map-modal.js"' in page
    assert 'src="/static/js/src/explorer-copy.js"' in page
    assert 'id="map-modal"' in page
    assert "data-map-modal-trigger" in page
    assert 'data-copy-text="https://hdl.handle.net/test/query-opt-92"' in page
    assert ">hdl:test/query-opt-92<" in page
    assert "onclick=\"navigator.clipboard" not in page
    assert "hx-on::after-request" not in page
    assert "hx-on::before-request" not in page


@pytest.mark.django_db
def test_collection_list_grouped_map_popup_scroll_is_contained(client):
    _build_collection_graph(94)

    response = client.get(reverse("explorer:collection_list"))

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    # Popup container styling stays inline in the template.
    assert "max-height: 300px" in page
    assert 'font-family: "Albert Sans", system-ui, sans-serif' in page
    assert "collection-item" in page
    assert "overscroll-behavior: contain" in page
    # The map behaviour is loaded from the extracted static module.
    assert 'src="/static/js/src/collections-map.js"' in page
    # The scroll-containment logic now lives in that module.
    module_path = finders.find("js/src/collections-map.js")
    assert module_path is not None
    module_src = Path(module_path).read_text(encoding="utf-8")
    assert "function containPopupScroll(popup)" in module_src
    assert "element.querySelector('.maplibregl-popup-content')" in module_src
    assert "event.stopPropagation();" in module_src


@pytest.mark.django_db
def test_faceted_collection_table_renders_map_trigger_for_geo_location(client):
    collection = _build_collection_graph(93)
    location = collection.general_info.first().location
    location.region_facet = "Region"
    location.country_facet = "Country"
    location.save(update_fields=["region_facet", "country_facet"])

    response = client.get("/search/")

    assert response.status_code == 200
    page = response.content.decode("utf-8")
    assert "data-map-modal-trigger" in page
    assert 'hx-target="#map-modal-content"' in page
    assert f"geo={location.geo_location}" in page
