from __future__ import annotations

import re
from typing import Iterable

import bleach
import markdown


MARKDOWN_EXTENSIONS = ("tables", "fenced_code", "toc", "nl2br")

SAFE_HTML_TAGS = sorted(
    set(bleach.sanitizer.ALLOWED_TAGS).union(
        {
            "p",
            "pre",
            "code",
            "blockquote",
            "hr",
            "br",
            "span",
            "div",
            "img",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "ul",
            "ol",
            "li",
        },
    ),
)

SAFE_HTML_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "*": ["id"],
    "a": ["href", "title"],
    "code": ["class"],
    "div": ["class"],
    "img": ["src", "alt", "title"],
    "span": ["class"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

SAFE_HTML_PROTOCOLS = set(bleach.sanitizer.ALLOWED_PROTOCOLS).union({"mailto"})
STRIP_BLOCK_TAGS_RE = re.compile(
    r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_html(html: str) -> str:
    """Return a sanitized HTML fragment safe for template rendering."""
    cleaned_html = STRIP_BLOCK_TAGS_RE.sub("", html)
    return bleach.clean(
        cleaned_html,
        tags=SAFE_HTML_TAGS,
        attributes=SAFE_HTML_ATTRIBUTES,
        protocols=SAFE_HTML_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


def render_safe_markdown(
    text: str,
    *,
    extensions: Iterable[str] = MARKDOWN_EXTENSIONS,
) -> str:
    """Render Markdown to sanitized HTML."""
    rendered = markdown.markdown(text, extensions=list(extensions))
    return sanitize_html(rendered)
