from __future__ import annotations

from lacos.storage.constants import WAC_AGENT, WAC_AUTHENTICATED_AGENT

# Ordered list of urn:lacos: sub-prefixes and their display transforms.
# Each entry is (prefix_to_strip, replacement_prefix).
# An empty replacement means the prefix is simply removed.
_URN_LACOS_SUBPREFIXES: tuple[tuple[str, str], ...] = (
    ("urn:lacos:eppn:", ""),
    ("urn:lacos:user:", "user:"),
    ("urn:lacos:agent:", "agent:"),
    ("urn:lacos:group:", "group:"),
)


def format_agent_uri_for_display(uri: str | None) -> str:
    """
    Convert a full agent URI to a human-readable short form for display.

    - foaf:Agent           -> "Everyone"
    - acl:AuthenticatedAgent -> "Authenticated"
    - urn:lacos:eppn:x     -> "x"
    - urn:lacos:user:x     -> "user:x"
    - urn:lacos:agent:x    -> "agent:x"
    - urn:lacos:group:x    -> "group:x"
    - mailto:, http://, https:// and anything else -> returned as-is
    - None / empty          -> ""
    """
    if not uri or not uri.strip():
        return ""

    if uri == WAC_AGENT:
        return "Everyone"

    if uri == WAC_AUTHENTICATED_AGENT:
        return "Authenticated"

    for prefix, replacement in _URN_LACOS_SUBPREFIXES:
        if uri.startswith(prefix):
            return f"{replacement}{uri[len(prefix):]}"

    return uri
