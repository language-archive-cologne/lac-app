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
