from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from lacos.storage.constants import (
    ACL_LEVEL_EMBARGO,
    ACL_LEVEL_PRIVATE,
    ACL_LEVEL_PROTECTED,
    ACL_LEVEL_PUBLIC,
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
        - Protected:  Contains acl:AuthenticatedAgent with acl:Read
        - Private:    Contains specific agent(s) with acl:Read
        - Embargo:    No readable entries
    """
    if not entries:
        return ACL_LEVEL_EMBARGO

    has_public = False
    has_authenticated = False
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
            has_authenticated = True
        elif isinstance(agent, str) and agent:
            has_person = True

    if has_public:
        return ACL_LEVEL_PUBLIC
    if has_authenticated:
        return ACL_LEVEL_PROTECTED
    if has_person:
        return ACL_LEVEL_PRIVATE
    return ACL_LEVEL_EMBARGO


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
