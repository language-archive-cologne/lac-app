from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from lacos.utils.text import normalize_nfc
from lacos.storage.constants import (
    ACL_LEVEL_ACADEMIC,
    ACL_LEVEL_PUBLIC,
    ACL_LEVEL_RESTRICTED,
    WAC_AGENT,
    WAC_AUTHENTICATED_AGENT,
    WAC_READ,
)


def _has_mode_read(entry: Mapping[str, object]) -> bool:
    """
    Internal helper to determine whether an ACL entry grants read access.
    """
    modes = entry.get("mode")
    if not isinstance(modes, Sequence):
        return False
    return WAC_READ in modes


def determine_access_level(entries: Iterable[Mapping[str, object]] | None) -> str:
    """
    Determine the high-level access level represented by a list of ACL entries.

    The logic mirrors the access levels from the legacy KA3 API:
        - Public:     Contains foaf:Agent with acl:Read
        - Academic:   Contains acl:AuthenticatedAgent with acl:Read
        - Restricted: Contains specific agent(s) with acl:Read or no readable entries
    """
    if not entries:
        return ACL_LEVEL_RESTRICTED

    has_public = False
    has_academic = False
    has_person = False

    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if not _has_mode_read(entry):
            continue

        agent_class = entry.get("agentClass")
        agent = entry.get("agent")

        if agent_class == WAC_AGENT:
            has_public = True
        elif agent_class == WAC_AUTHENTICATED_AGENT:
            has_academic = True
        elif isinstance(agent, str) and agent:
            has_person = True

    if has_public:
        return ACL_LEVEL_PUBLIC
    if has_academic:
        return ACL_LEVEL_ACADEMIC
    if has_person:
        return ACL_LEVEL_RESTRICTED
    return ACL_LEVEL_RESTRICTED


def extract_read_agents(entries: Iterable[Mapping[str, object]] | None) -> list[str]:
    """
    Collect all agents/agent classes that have acl:Read permission.
    """
    if not entries:
        return []

    agents: list[str] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        if not _has_mode_read(entry):
            continue

        agent = entry.get("agent")
        agent_class = entry.get("agentClass")

        if isinstance(agent, str) and agent:
            agents.append(agent)
        if isinstance(agent_class, str) and agent_class:
            agents.append(agent_class)

    # Preserve order while deduplicating
    return list(dict.fromkeys(agents))


# Known URI prefixes that should be preserved as-is
_KNOWN_PREFIXES = (
    "urn:lacos:",  # Our format
    "mailto:",
    "https://",
    "http://",
    "urn:",  # Other URN schemes
)


def normalize_agent_uri(uri: str | None) -> str | None:
    """
    Normalize an agent URI to our urn:lacos: format.

    - Applies Unicode NFC normalization for consistent character representation
    - URIs with known prefixes (mailto:, https://, urn:, etc.) are preserved
    - URIs that look like eppn (contain @, no prefix) become urn:lacos:eppn:<uri>
    - Other plain strings become urn:lacos:agent:<uri>

    Returns None if uri is None or empty.
    """
    if not uri:
        return None

    uri = normalize_nfc(uri.strip())
    if not uri:
        return None

    # Already has a known prefix - keep as-is
    for prefix in _KNOWN_PREFIXES:
        if uri.startswith(prefix):
            return uri

    # Looks like an eppn (email-like format) - normalize to urn:lacos:eppn:
    if "@" in uri:
        return f"urn:lacos:eppn:{uri}"

    # Other plain string - normalize to urn:lacos:agent:
    return f"urn:lacos:agent:{uri}"


def normalize_permissions_data(
    entries: Sequence[dict[str, object]] | None,
) -> list[dict[str, object]] | None:
    """
    Normalize all agent URIs in a permissions data list.

    Returns a new list with normalized URIs, or None if input is None.
    """
    if entries is None:
        return None

    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            normalized.append(entry)
            continue

        new_entry = dict(entry)
        agent = entry.get("agent")
        if isinstance(agent, str):
            new_entry["agent"] = normalize_agent_uri(agent)

        normalized.append(new_entry)

    return normalized
