from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory


def _render_resource_detail():
    """Render the full-page media player template with a minimal context."""
    request = RequestFactory().get("/explorer/resource/test/")
    context = {
        "resource_name": "sample.wav",
        "media_type": "audio",
        "download_bucket": "bucket",
        "download_key": "path/to/sample.wav",
        "download_filename": "sample.wav",
    }
    return render_to_string("resource_detail.html", context, request=request)


def test_full_page_player_includes_single_file_download_modal():
    """The full-page player must render the single-file download dialog.

    Regression test for work item #162: the download button on the full-page
    media player did nothing because the dialog component was never included
    (unlike the modal player on collection/bundle detail pages).
    """
    html = _render_resource_detail()

    assert 'id="single-file-download-modal"' in html


def test_full_page_player_wires_single_download_button_handler():
    """The full-page player must register the delegated download click handler."""
    html = _render_resource_detail()

    assert "single-download-btn" in html
    assert "singleFileDownloadModal" in html


def test_resource_breadcrumb_uses_resolved_title_without_related_lookup():
    class UnexpectedRelatedLookup:
        first_accessed = False

        @property
        def first(self):
            self.first_accessed = True
            return SimpleNamespace(display_title="Unexpected related title")

    request = RequestFactory().get("/resource/11341/test-resource/")
    related_lookup = UnexpectedRelatedLookup()
    context = {
        "resource_name": "sample.wav",
        "media_type": "audio",
        "parent_title": "Resolved bundle title",
        "bundle": SimpleNamespace(
            handle_path="11341/test-bundle",
            identifier="hdl:11341/test-bundle",
            general_info=related_lookup,
        ),
    }

    html = render_to_string("resource_detail.html", context, request=request)

    assert "Resolved bundle title" in html
    assert related_lookup.first_accessed is False
