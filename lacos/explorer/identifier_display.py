"""Formatting utilities for creator name identifiers (ORCID, ISNI, EMAIL, etc.)."""

from django.utils.html import escape

ORCID_SVG = (
    '<svg class="w-3 h-3" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">'
    '<path fill="#A6CE39" d="M256 128c0 70.7-57.3 128-128 128S0 198.7 0 128S57.3 0 128 0s128 57.3 128 128"/>'
    '<path fill="#fff" d="M86.3 186.2H70.9V79.1h15.4zm22.6 0h45.5c35.6 0 53.4-21.9 53.4-53.1s-17.8-54-53.4-54h-45.5zm15.4-92.4h26.5c26.6 0 40.7 14.9 40.7 39.3s-14.1 38.4-40.7 38.4h-26.5zm-38-36.6c0 5.5-4.5 10-10.1 10s-10.1-4.5-10.1-10s4.5-10 10.1-10s10.1 4.5 10.1 10"/>'
    "</svg>"
)

ORCID_PREFIXES = ("https://orcid.org/", "http://orcid.org/")
ISNI_PREFIXES = (
    "https://www.isni.org/",
    "http://www.isni.org/",
    "https://isni.org/isni/",
    "http://isni.org/isni/",
)


def extract_short_id(identifier: str, identifier_type: str) -> str:
    """Extract the bare ID from a full URL, or return as-is if already bare."""
    if not identifier:
        return ""
    identifier = identifier.strip()
    id_type = (identifier_type or "").upper()

    if id_type == "ORCID":
        for prefix in ORCID_PREFIXES:
            if identifier.startswith(prefix):
                return identifier[len(prefix) :].strip("/")
    elif id_type == "ISNI":
        for prefix in ISNI_PREFIXES:
            if identifier.startswith(prefix):
                return identifier[len(prefix) :].strip("/")
    return identifier


def build_full_url(short_id: str, identifier_type: str) -> str | None:
    """Build the canonical URL for a given short ID and type."""
    if not short_id:
        return None
    id_type = (identifier_type or "").upper()

    if id_type == "ORCID":
        return f"https://orcid.org/{short_id}"
    elif id_type == "ISNI":
        return f"https://www.isni.org/{short_id}"
    elif id_type == "EMAIL":
        return f"mailto:{short_id}"
    return None


def format_identifier_html(identifier: str, identifier_type: str) -> str:
    """Return an HTML snippet for displaying a creator identifier."""
    if not identifier or not identifier.strip():
        return ""

    id_type = (identifier_type or "").upper()
    # Email addresses should not be rendered in public metadata blocks.
    if id_type == "EMAIL":
        return ""

    short_id = extract_short_id(identifier, id_type)
    url = build_full_url(short_id, id_type)
    escaped_id = escape(short_id)

    link_classes = "inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"

    if id_type == "ORCID" and url:
        return (
            f'<a href="{escape(url)}" target="_blank" rel="noopener" class="{link_classes}">'
            f"{ORCID_SVG} {escaped_id}</a>"
        )
    elif id_type == "ISNI" and url:
        return (
            f'<a href="{escape(url)}" target="_blank" rel="noopener" class="{link_classes}">'
            f"ISNI: {escaped_id}</a>"
        )
    else:
        return f'<span class="inline-flex items-center text-xs text-base-content/60 mt-1">{escaped_id}</span>'
