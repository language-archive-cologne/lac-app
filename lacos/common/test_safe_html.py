from lacos.common.services.safe_html import render_safe_markdown, sanitize_html


def test_render_safe_markdown_removes_active_content():
    html = render_safe_markdown(
        '[click me](javascript:alert(1))<script>alert(1)</script><img src="x" onerror="alert(1)">',
    )

    assert "javascript:" not in html
    assert "<script" not in html
    assert "alert(1)" not in html
    assert "onerror" not in html


def test_sanitize_html_preserves_safe_table_markup():
    html = sanitize_html("<table><tr><td>ok</td></tr></table>")

    assert "<table>" in html
    assert "<td>ok</td>" in html


def test_sanitize_html_removes_script_block_contents():
    html = sanitize_html("<div>before</div><script>alert(1)</script><p>after</p>")

    assert "alert(1)" not in html
    assert "<script" not in html
    assert "<p>after</p>" in html
