import pytest
from django.urls import reverse

from lacos.explorer.templatetags.explorer_extras import urlize_text
from lacos.explorer.tests.test_collection_list_query_optimization import _build_collection_graph


def test_urlize_text_escapes_html_before_linkifying():
    rendered = str(urlize_text('<img src=x onerror=alert(1)> https://example.com'))

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert 'href="https://example.com"' in rendered


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
