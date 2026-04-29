import re
from pathlib import Path

from django.template.loader import render_to_string

from lacos.common.mixins.htmx_template_helpers import ROOT_FOLDER_SENTINEL
from lacos.storage.services.collection_service import BucketListingPage


INLINE_HANDLER_PATTERN = re.compile(
    r"\s(?:on[a-z]+|hx-on(?:::[a-z-]+)?|style)\s*=",
    re.IGNORECASE,
)
SUMMARY_PATTERN = re.compile(r"<summary\b[\s\S]*?</summary>", re.IGNORECASE)
INTERACTIVE_ELEMENT_PATTERN = re.compile(
    r"<(?:a|button|input|label|select|textarea)\b",
    re.IGNORECASE,
)


def _assert_no_inline_handlers(html: str):
    assert INLINE_HANDLER_PATTERN.search(html) is None


def _assert_no_interactive_elements_in_summary(html: str):
    for summary in SUMMARY_PATTERN.findall(html):
        assert INTERACTIVE_ELEMENT_PATTERN.search(summary) is None


def test_archivist_dashboard_template_uses_external_dashboard_scripts():
    template = Path("lacos/storage/templates/dashboard/archivist_dashboard.html")
    html = template.read_text()

    _assert_no_inline_handlers(html)
    assert "<script>" not in html
    assert "js/src/storage-dashboard.js" in html


def test_upload_config_bridge_uses_external_script():
    template = Path("lacos/storage/templates/upload/_upload_config_bridge.html")
    html = template.read_text()

    assert "<script>" not in html
    assert "js/src/upload-config-bridge.js" in html


def test_base_template_prevents_htmx_and_altcha_inline_style_injection():
    html = Path("lacos/templates/base.html").read_text()

    assert '"includeIndicatorStyles":false' in html
    assert 'id="__altcha-css"' in html
    assert "vendor/css/altcha.css" in html


def test_folder_contents_partial_has_no_inline_event_handlers():
    listing = BucketListingPage(
        items=[
            {
                "type": "folder",
                "name": "collection-a",
                "path": "collection-a/",
            },
            {
                "type": "file",
                "name": "metadata.xml",
                "path": "collection-a/metadata.xml",
            },
        ],
        has_more=True,
        next_token="token-1",
        bucket="lacos-ingest",
        prefix="",
    )

    html = render_to_string(
        "dashboard/folder_contents_partial.html",
        {
            "listing": listing,
            "folder_path": "",
            "folder_path_param": ROOT_FOLDER_SENTINEL,
            "bucket_type": "lacos-ingest",
            "max_keys": 200,
            "is_root": True,
            "root_folder_sentinel": ROOT_FOLDER_SENTINEL,
            "csrf_token": "token",
        },
    )

    _assert_no_inline_handlers(html)
    _assert_no_interactive_elements_in_summary(html)
    assert "<summary" not in html
    assert "data-folder-toggle" in html
    assert "data-open-file-viewer" in html
    assert "data-remove-on-success" in html


def test_file_viewer_partials_have_no_inline_script_execution():
    modal_html = Path(
        "lacos/storage/templates/dashboard/partials/file_viewer_modal.html",
    ).read_text()
    error_html = Path(
        "lacos/storage/templates/dashboard/partials/file_viewer_error.html",
    ).read_text()

    _assert_no_inline_handlers(modal_html)
    _assert_no_inline_handlers(error_html)
    assert "<script>" not in modal_html
    assert "data-close-file-viewer" in modal_html
    assert "data-close-file-viewer" in error_html
