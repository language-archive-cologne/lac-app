from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from huey.contrib.djhuey import task

from lacos.common.services.safe_html import sanitize_html

logger = logging.getLogger(__name__)


def _get_latest_tag(repo_url: str) -> str | None:
    """Query remote repo for latest tag sorted by version."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--sort=-v:refname", repo_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("Failed to query tags: %s", result.stderr)
            return None

        # Parse first line: <sha>\trefs/tags/guidelines-v1.0.0
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            match = re.search(r"refs/tags/(.+)$", line)
            if match:
                tag = match.group(1)
                # Skip ^{} dereferenced tags
                if not tag.endswith("^{}"):
                    return tag
        return None
    except subprocess.TimeoutExpired:
        logger.error("Timeout querying tags from %s", repo_url)
        return None
    except Exception as exc:
        logger.error("Error querying tags: %s", exc)
        return None


def _get_local_latest_tag(repo_path: Path) -> str | None:
    """Get latest tag from a local git repository."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(repo_path),
        )
        if result.returncode != 0:
            logger.error("Failed to get local tags: %s", result.stderr)
            return None
        return result.stdout.strip()
    except Exception as exc:
        logger.error("Error getting local tags: %s", exc)
        return None


def _clone_tag(repo_url: str, tag: str, dest: Path) -> bool:
    """Clone a specific tag to destination directory."""
    try:
        result = subprocess.run(
            ["git", "clone", "--branch", tag, "--depth", "1", repo_url, str(dest)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("Failed to clone tag %s: %s", tag, result.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("Timeout cloning tag %s", tag)
        return False
    except Exception as exc:
        logger.error("Error cloning tag %s: %s", tag, exc)
        return False


def _fix_internal_links(html: str) -> str:
    """Convert internal .md links to proper URL paths."""
    # Map from MD filename (without extension) to URL slug
    file_to_slug = {
        "submission": "submission-guidelines",
        "whitelist": "format-whitelist",
        "archiving_LAC": "archiving",
        "licenses": "licenses",
        "user": "user",
    }

    def replace_link(match: re.Match) -> str:
        md_file = match.group(1)
        file_stem = md_file.replace(".md", "")
        slug = file_to_slug.get(file_stem, file_stem.replace("_", "-"))
        return f'href="/user-guides/{slug}/"'

    # Replace href="*.md" with proper URLs
    return re.sub(r'href="([^"]+\.md)"', replace_link, html)


def _render_markdown_files(texts_dir: Path, output_dir: Path, tag: str) -> dict:
    """Render all MD files to HTML."""
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered = []
    errors = []

    for md_file in texts_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            html = sanitize_html(_fix_internal_links(content_to_html(content)))
            slug = md_file.stem
            output_path = output_dir / f"{slug}.html"
            output_path.write_text(html, encoding="utf-8")
            rendered.append(slug)
            logger.info("Rendered %s.md -> %s.html", slug, slug)
        except Exception as exc:
            errors.append({"file": md_file.name, "error": str(exc)})
            logger.error("Failed to render %s: %s", md_file.name, exc)

    # Write version file with tag info
    version_file = output_dir / "VERSION"
    version_file.write_text(tag, encoding="utf-8")
    logger.info("Wrote version file: %s", tag)

    return {"rendered": rendered, "errors": errors}


def content_to_html(content: str) -> str:
    from lacos.common.services.safe_html import render_safe_markdown

    return render_safe_markdown(
        content,
        extensions=["tables", "fenced_code", "toc"],
    )


@task(retries=2, retry_delay=60)
def sync_guidelines() -> dict:
    """
    Fetch latest tag from lac-guidelines, render MD to HTML, write to filesystem.

    Supports both:
    - Remote git URL (production): clones the repo
    - Local path (development): reads directly from mounted volume

    Returns dict with success status and details.
    """
    repo_url = getattr(settings, "GUIDELINES_REPO_URL", None)
    output_dir = getattr(settings, "GUIDELINES_HTML_DIR", None)

    if not repo_url:
        return {"success": False, "error": "GUIDELINES_REPO_URL not configured"}

    if not output_dir:
        return {"success": False, "error": "GUIDELINES_HTML_DIR not configured"}

    output_dir = Path(output_dir)

    # Check if using local path (starts with /)
    is_local = repo_url.startswith("/")

    if is_local:
        # Local development mode - read directly from mounted volume
        local_path = Path(repo_url)
        if not local_path.exists():
            return {"success": False, "error": f"Local path does not exist: {repo_url}"}

        # Try env var first (set by CI), then git describe, then fallback
        tag = os.environ.get("GUIDELINES_TAG") or _get_local_latest_tag(local_path)
        if not tag:
            tag = "local-dev"

        logger.info("Using local path: %s (tag: %s)", repo_url, tag)

        texts_dir = local_path / "texts"
        if not texts_dir.exists():
            return {"success": False, "error": "No 'texts' directory in local path"}

        result = _render_markdown_files(texts_dir, output_dir, tag)
    else:
        # Production mode - clone from remote
        logger.info("Querying latest tag from %s", repo_url)
        tag = _get_latest_tag(repo_url)
        if not tag:
            return {"success": False, "error": "No tags found in repository"}

        logger.info("Latest tag: %s", tag)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            if not _clone_tag(repo_url, tag, tmp_path):
                return {"success": False, "error": f"Failed to clone tag {tag}"}

            texts_dir = tmp_path / "texts"
            if not texts_dir.exists():
                return {"success": False, "error": "No 'texts' directory in repository"}

            result = _render_markdown_files(texts_dir, output_dir, tag)

    return {
        "success": True,
        "tag": tag,
        "rendered": result["rendered"],
        "errors": result["errors"],
        "output_dir": str(output_dir),
    }


# Ensure DB backup tasks are registered with Huey.
from lacos.common.db_backup_tasks import (  # noqa: E402,F401
    backup_database_to_s3,
    backup_database_to_s3_periodic,
)
