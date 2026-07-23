"""Tests for guideline sync link rewriting (issue #156)."""
from lacos.common.tasks import _fix_internal_links


def test_fix_internal_links_uses_title_aligned_slugs():
    html = (
        '<a href="archiving_LAC.md">Archiving</a> '
        '<a href="licenses.md">Licenses</a>'
    )

    result = _fix_internal_links(html)

    assert 'href="/user-guides/archiving/"' in result
    assert 'href="/user-guides/licenses/"' in result
    # Legacy slugs must no longer be emitted into rendered guideline content.
    assert "depositing-policy" not in result
    assert "depositor-agreement" not in result


def test_fix_internal_links_falls_back_to_dash_slug():
    html = '<a href="some_other_file.md">Other</a>'

    result = _fix_internal_links(html)

    assert 'href="/user-guides/some-other-file/"' in result


def test_fix_asset_urls_rewrites_relative_asset_sources():
    from lacos.common.tasks import _fix_asset_urls

    html = '<img alt="flowchart" src="assets/keyword_categories.png">'

    result = _fix_asset_urls(html)

    assert 'src="/user-guides/assets/keyword_categories.png"' in result


def test_fix_asset_urls_leaves_other_sources_alone():
    from lacos.common.tasks import _fix_asset_urls

    html = '<img src="https://example.org/pic.png"> <img src="/static/x.png">'

    assert _fix_asset_urls(html) == html


def test_render_markdown_files_copies_assets_and_rewrites_sources(tmp_path):
    from lacos.common.tasks import _render_markdown_files

    texts_dir = tmp_path / "texts"
    assets_dir = texts_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "pic.png").write_bytes(b"\x89PNG fake")
    (texts_dir / "guide.md").write_text(
        "# Guide\n\n![a picture](assets/pic.png)\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    result = _render_markdown_files(texts_dir, output_dir, "test-tag")

    assert result["rendered"] == ["guide"]
    assert (output_dir / "assets" / "pic.png").read_bytes() == b"\x89PNG fake"
    html = (output_dir / "guide.html").read_text(encoding="utf-8")
    assert 'src="/user-guides/assets/pic.png"' in html
