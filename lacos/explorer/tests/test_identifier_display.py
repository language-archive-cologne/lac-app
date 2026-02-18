import pytest

from lacos.explorer.identifier_display import (
    build_full_url,
    extract_short_id,
    format_identifier_html,
)


# ---------------------------------------------------------------------------
# extract_short_id
# ---------------------------------------------------------------------------

class TestExtractShortId:
    def test_orcid_bare_id(self):
        assert extract_short_id("0000-0002-1825-0097", "ORCID") == "0000-0002-1825-0097"

    def test_orcid_full_url(self):
        assert extract_short_id("https://orcid.org/0000-0002-1825-0097", "ORCID") == "0000-0002-1825-0097"

    def test_orcid_full_url_trailing_slash(self):
        assert extract_short_id("https://orcid.org/0000-0002-1825-0097/", "ORCID") == "0000-0002-1825-0097"

    def test_isni_bare_id(self):
        assert extract_short_id("000000012347926X", "ISNI") == "000000012347926X"

    def test_isni_www_url(self):
        assert extract_short_id("https://www.isni.org/000000012347926X", "ISNI") == "000000012347926X"

    def test_isni_isni_org_url(self):
        assert extract_short_id("https://isni.org/isni/000000012347926X", "ISNI") == "000000012347926X"

    def test_email_returns_as_is(self):
        assert extract_short_id("user@example.com", "EMAIL") == "user@example.com"

    def test_other_returns_as_is(self):
        assert extract_short_id("some-id-123", "OTHER") == "some-id-123"

    def test_none_identifier(self):
        assert extract_short_id(None, "ORCID") == ""

    def test_empty_string(self):
        assert extract_short_id("", "ORCID") == ""

    def test_whitespace_only(self):
        assert extract_short_id("   ", "ORCID") == ""

    def test_none_type(self):
        assert extract_short_id("some-id", None) == "some-id"

    def test_case_insensitive_type(self):
        assert extract_short_id("https://orcid.org/0000-0002-1825-0097", "orcid") == "0000-0002-1825-0097"


# ---------------------------------------------------------------------------
# build_full_url
# ---------------------------------------------------------------------------

class TestBuildFullUrl:
    def test_orcid(self):
        assert build_full_url("0000-0002-1825-0097", "ORCID") == "https://orcid.org/0000-0002-1825-0097"

    def test_isni(self):
        assert build_full_url("000000012347926X", "ISNI") == "https://www.isni.org/000000012347926X"

    def test_email(self):
        assert build_full_url("user@example.com", "EMAIL") == "mailto:user@example.com"

    def test_other_returns_none(self):
        assert build_full_url("some-id", "OTHER") is None

    def test_empty_id_returns_none(self):
        assert build_full_url("", "ORCID") is None

    def test_none_type(self):
        assert build_full_url("some-id", None) is None

    def test_case_insensitive_type(self):
        assert build_full_url("0000-0002-1825-0097", "orcid") == "https://orcid.org/0000-0002-1825-0097"


# ---------------------------------------------------------------------------
# format_identifier_html
# ---------------------------------------------------------------------------

class TestFormatIdentifierHtml:
    # --- ORCID ---

    def test_orcid_bare_id_contains_svg(self):
        html = format_identifier_html("0000-0002-1825-0097", "ORCID")
        assert "<svg" in html
        assert "A6CE39" in html

    def test_orcid_bare_id_link(self):
        html = format_identifier_html("0000-0002-1825-0097", "ORCID")
        assert 'href="https://orcid.org/0000-0002-1825-0097"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener"' in html
        assert "0000-0002-1825-0097" in html

    def test_orcid_full_url_extracts_short_id(self):
        html = format_identifier_html("https://orcid.org/0000-0002-1825-0097", "ORCID")
        assert 'href="https://orcid.org/0000-0002-1825-0097"' in html
        # The displayed text should be the short ID, not the full URL
        assert html.count("https://orcid.org/0000-0002-1825-0097") == 1  # only in href

    # --- ISNI ---

    def test_isni_bare_id(self):
        html = format_identifier_html("000000012347926X", "ISNI")
        assert "ISNI:" in html
        assert "000000012347926X" in html
        assert 'href="https://www.isni.org/000000012347926X"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener"' in html

    def test_isni_full_url_extracts_short_id(self):
        html = format_identifier_html("https://www.isni.org/000000012347926X", "ISNI")
        assert "ISNI: 000000012347926X" in html
        assert 'href="https://www.isni.org/000000012347926X"' in html

    def test_isni_isni_org_variant(self):
        html = format_identifier_html("https://isni.org/isni/000000012347926X", "ISNI")
        assert "ISNI: 000000012347926X" in html

    # --- EMAIL ---

    def test_email_not_rendered(self):
        html = format_identifier_html("user@example.com", "EMAIL")
        assert html == ""

    def test_email_not_rendered_for_mailto_value(self):
        html = format_identifier_html("mailto:user@example.com", "EMAIL")
        assert html == ""

    def test_email_no_target_blank(self):
        html = format_identifier_html("user@example.com", "EMAIL")
        assert 'target="_blank"' not in html

    # --- OTHER ---

    def test_other_plain_text(self):
        html = format_identifier_html("some-id-123", "OTHER")
        assert "<span" in html
        assert "some-id-123" in html
        assert "<a" not in html

    # --- Edge cases ---

    def test_none_returns_empty(self):
        assert format_identifier_html(None, "ORCID") == ""

    def test_empty_string_returns_empty(self):
        assert format_identifier_html("", "ORCID") == ""

    def test_whitespace_only_returns_empty(self):
        assert format_identifier_html("   ", "ORCID") == ""

    def test_unknown_type_renders_as_span(self):
        html = format_identifier_html("xyz-123", "UNKNOWN")
        assert "<span" in html
        assert "xyz-123" in html

    def test_none_type_renders_as_span(self):
        html = format_identifier_html("xyz-123", None)
        assert "<span" in html

    def test_html_escaping(self):
        html = format_identifier_html('<script>alert("xss")</script>', "OTHER")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
