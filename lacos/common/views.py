import re
from pathlib import Path

from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from lacos.common.services.safe_html import sanitize_html


# Mapping from URL slug to MD filename (without extension)
# Maps URL slugs to filenames in lac-guidelines/texts/
GUIDELINE_SLUG_MAP = {
    "submission-guidelines": "submission",
    "format-whitelist": "whitelist",
    "depositing-policy": "archiving_LAC",
    "depositor-agreement": "licenses",
    "licenses": "licenses",
    "user": "user",
    "archiving": "archiving_LAC",
}


def _extract_title_and_strip(html: str) -> tuple[str | None, str]:
    """Extract title from first <h1> tag and return content without it."""
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if match:
        # Strip any HTML tags from within the title
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        # Remove the <h1> from content to avoid duplication
        content = html[:match.start()] + html[match.end():]
        return title, content.strip()
    return None, html


def _slug_to_title(slug: str) -> str:
    """Convert URL slug to display title (fallback)."""
    return slug.replace("-", " ").replace("_", " ").title()


def _get_guidelines_version(html_dir: Path) -> str | None:
    """Read the VERSION file to get the current guidelines tag."""
    version_file = html_dir / "VERSION"
    if version_file.exists():
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except Exception:
            return None
    return None


def guideline_view(request, slug: str):
    """
    Serve guideline content from rendered MD files.

    Only serves pages that have MD files in lac-guidelines/texts/.
    Returns 404 if no MD file exists for the slug.
    Title is extracted from the MD file's # heading.
    """
    # Get the file slug (may differ from URL slug)
    file_slug = GUIDELINE_SLUG_MAP.get(slug, slug.replace("-", "_"))

    # Check for rendered HTML file
    html_dir = getattr(settings, "GUIDELINES_HTML_DIR", None)
    if not html_dir:
        raise Http404("Guidelines not configured")

    html_dir = Path(html_dir)
    html_path = html_dir / f"{file_slug}.html"

    if not html_path.exists():
        raise Http404(f"Guideline '{slug}' not found")

    raw_content = sanitize_html(html_path.read_text(encoding="utf-8"))

    # Extract title from content's <h1> and strip it from content
    title, content = _extract_title_and_strip(raw_content)
    title = title or _slug_to_title(slug)

    version = _get_guidelines_version(html_dir)

    return render(
        request,
        "pages/user_guides/base_guide_dynamic.html",
        {"content": content, "title": title, "version": version},
    )
