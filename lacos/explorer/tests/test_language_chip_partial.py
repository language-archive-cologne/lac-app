"""Pin the language chip partial's output."""
import pytest
from django.template.loader import render_to_string


class _Language:
    def __init__(self, name, iso):
        self.name = name
        self.iso_639_3_code = iso


@pytest.mark.django_db
def test_language_chip_renders_iso_and_glottolog():
    html = render_to_string(
        "explorer/partials/language_chip.html",
        {"language": _Language("Pnar", "pbv")},
    )
    assert "Pnar" in html
    assert "[pbv]" in html
    assert "glottolog.org/resource/languoid/iso/pbv" in html


@pytest.mark.django_db
def test_language_chip_without_iso_has_no_glottolog():
    html = render_to_string(
        "explorer/partials/language_chip.html",
        {"language": _Language("Unattested", "")},
    )
    assert "Unattested" in html
    assert "glottolog.org" not in html


@pytest.mark.django_db
def test_keyword_chip_renders_value():
    html = render_to_string(
        "explorer/partials/keyword_chip.html",
        {"value": "fieldwork"},
    )
    assert "fieldwork" in html
    assert "rounded-md" in html
