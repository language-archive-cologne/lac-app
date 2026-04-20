"""Pin the language chip partial's output."""
from pathlib import Path

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
    assert "language-chip inline-flex items-center rounded-md border" in html
    assert "language-chip-iso text-[10.5px] tabular-nums leading-none" in html


@pytest.mark.django_db
def test_language_chip_without_iso_has_no_glottolog():
    html = render_to_string(
        "explorer/partials/language_chip.html",
        {"language": _Language("Unattested", "")},
    )
    assert "Unattested" in html
    assert "glottolog.org" not in html


@pytest.mark.django_db
def test_small_language_chip_matches_refined_list_typography():
    html = render_to_string(
        "explorer/partials/language_chip.html",
        {"language": _Language("Pnar", "pbv"), "size": "sm"},
    )
    assert "gap-1 px-2 py-[3px] text-xs" in html
    assert "leading-none" in html
    assert "glottolog.org" not in html


def test_language_chip_component_styles_use_refined_neutrals():
    css = Path("theme/static_src/css/input.css").read_text()

    assert ".language-chip {" in css
    assert "background: #f6f6f6;" in css
    assert "border-color: var(--color-base-300);" in css
    assert ".language-chip-iso {" in css
    assert "color: color-mix(in oklab, var(--color-base-content) 55%, transparent);" in css


@pytest.mark.django_db
def test_keyword_chip_renders_value():
    html = render_to_string(
        "explorer/partials/keyword_chip.html",
        {"value": "fieldwork"},
    )
    assert "fieldwork" in html
    assert "rounded-md" in html
