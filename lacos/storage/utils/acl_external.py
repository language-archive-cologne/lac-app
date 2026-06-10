"""
External serialization of ACL permissions data to the shared ``acl.json`` format.

``acl.json`` is the JSON exchange format shared between the curation pipeline
and the LACOS workbench. Its contract is WAC-aligned in semantics:

- concrete users are serialized as ``agent`` with the bare EPPN value
- public access is serialized as ``agentClass: "foaf:Agent"``
- authenticated access is serialized as ``agentClass: "acl:AuthenticatedAgent"``
- internal LACOS identifiers (``urn:lacos:eppn:*``, ``urn:lacos:agent:*``) and
  ``foaf:Person`` annotations are internal-only and must never be written out
- the external group representation is not decided yet, so group entries are
  passed through unchanged

The internal shape produced by ``lacos.storage.utils.acl.normalize_permissions_data``
stays untouched; this module only converts on the way out (DB -> S3).
"""

from __future__ import annotations

from typing import Any, Sequence

_EPPN_PREFIX = "urn:lacos:eppn:"
_AGENT_PREFIX = "urn:lacos:agent:"
_GROUP_PREFIX = "urn:lacos:group:"

_FOAF_PERSON = "foaf:Person"
_FOAF_GROUP = "foaf:Group"


def serialize_agent_for_acl_json(agent: str) -> str:
    """
    Convert an internal agent identifier to its external ``acl.json`` value.

    ``urn:lacos:eppn:`` and ``urn:lacos:agent:`` prefixes are stripped so the
    bare EPPN/identifier is written; any other value is returned unchanged.
    The conversion is round-trip safe: loading the bare value back through
    ``normalize_agent_uri`` restores the internal identifier.
    """
    for prefix in (_EPPN_PREFIX, _AGENT_PREFIX):
        if agent.startswith(prefix):
            return agent[len(prefix):]
    return agent


def _is_group_entry(entry: dict[str, Any]) -> bool:
    agent = entry.get("agent")
    if entry.get("agentClass") == _FOAF_GROUP:
        return True
    return isinstance(agent, str) and agent.startswith(_GROUP_PREFIX)


def serialize_permissions_data_for_acl_json(
    entries: Sequence[Any] | None,
) -> list[Any]:
    """
    Serialize internal permissions data for external ``acl.json`` write-back.

    Returns a new list (``[]`` for ``None`` input — external ``acl.json`` is
    always a list of rule objects) without mutating the input:

    - class-based rules (``foaf:Agent``, ``acl:AuthenticatedAgent``) unchanged
    - concrete agent rules get the bare agent value and lose any
      ``foaf:Person`` type annotation
    - group rules pass through unchanged until the external group
      representation is decided
    - non-dict entries pass through unchanged
    """
    if not entries:
        return []

    serialized: list[Any] = []
    for entry in entries:
        if not isinstance(entry, dict) or _is_group_entry(entry):
            serialized.append(entry)
            continue

        new_entry = dict(entry)
        agent = new_entry.get("agent")
        if isinstance(agent, str) and agent:
            new_entry["agent"] = serialize_agent_for_acl_json(agent)
            if new_entry.get("agentClass") == _FOAF_PERSON:
                del new_entry["agentClass"]

        serialized.append(new_entry)

    return serialized
