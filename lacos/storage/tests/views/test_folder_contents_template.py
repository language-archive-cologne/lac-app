import re

from django.template.loader import render_to_string

from lacos.common.mixins.htmx_template_helpers import ROOT_FOLDER_SENTINEL
from lacos.storage.services.collection_service import BucketListingPage


def _extract_load_more_button(html: str) -> str:
    match = re.search(
        r"<button[^>]*hx-get=\"[^\"]*continuation_token=[^\"]*\"[^>]*>.*?<span>Load more</span>\s*</button>",
        html,
        re.S,
    )
    assert match is not None, "Expected a load-more button in rendered HTML"
    return match.group(0)


def test_folder_contents_load_more_uses_append_swap_pattern():
    listing = BucketListingPage(
        items=[{"type": "file", "name": "item-1.txt", "path": "wooi_archive_cologne/item-1.txt"}],
        has_more=True,
        next_token="abc/def=",
        bucket="grails-dev",
        prefix="wooi_archive_cologne/",
    )

    html = render_to_string(
        "dashboard/folder_contents_partial.html",
        {
            "listing": listing,
            "folder_path": "wooi_archive_cologne/",
            "folder_path_param": "wooi_archive_cologne/",
            "bucket_type": "grails-dev",
            "max_keys": 200,
            "is_root": False,
            "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
            "csrf_token": "token",
        },
    )

    button_html = _extract_load_more_button(html)
    assert "continuation_token=abc/def%3D" in button_html
    assert 'hx-target="closest ul"' in button_html
    assert 'hx-swap="beforeend"' in button_html
    assert (
        'hx-on::after-request="if (event.detail.successful) { this.closest(\'li\')?.remove(); }"'
        in button_html
    )


def test_folder_contents_omits_load_more_when_not_paginated():
    listing = BucketListingPage(
        items=[{"type": "file", "name": "item-1.txt", "path": "wooi_archive_cologne/item-1.txt"}],
        has_more=False,
        next_token=None,
        bucket="grails-dev",
        prefix="wooi_archive_cologne/",
    )

    html = render_to_string(
        "dashboard/folder_contents_partial.html",
        {
            "listing": listing,
            "folder_path": "wooi_archive_cologne/",
            "folder_path_param": "wooi_archive_cologne/",
            "bucket_type": "grails-dev",
            "max_keys": 200,
            "is_root": False,
            "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
            "csrf_token": "token",
        },
    )

    assert "Load more" not in html


def test_folder_contents_load_more_regression_avoids_outerhtml_swap():
    listing = BucketListingPage(
        items=[{"type": "file", "name": "item-1.txt", "path": "wooi_archive_cologne/item-1.txt"}],
        has_more=True,
        next_token="token-1",
        bucket="grails-dev",
        prefix="wooi_archive_cologne/",
    )

    html = render_to_string(
        "dashboard/folder_contents_partial.html",
        {
            "listing": listing,
            "folder_path": "wooi_archive_cologne/",
            "folder_path_param": "wooi_archive_cologne/",
            "bucket_type": "grails-dev",
            "max_keys": 200,
            "is_root": False,
            "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
            "csrf_token": "token",
        },
    )

    button_html = _extract_load_more_button(html)
    assert 'hx-target="closest li"' not in button_html
    assert 'hx-swap="outerHTML"' not in button_html
    assert "hx-indicator=" not in button_html
