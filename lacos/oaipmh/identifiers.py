"""Helpers for parsing LACOS OAI-PMH identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .constants import REPO_IDENTIFIER

RecordKind = Literal["collection", "bundle"]


@dataclass(frozen=True)
class ParsedOAIIdentifier:
    kind: RecordKind
    local_identifier: str


def parse_oai_identifier(identifier: str | None) -> ParsedOAIIdentifier | None:
    """Return the local record identifier encoded in a LACOS OAI identifier."""

    if not identifier:
        return None

    collection_prefix = f"oai:{REPO_IDENTIFIER}:"
    bundle_prefix = f"{collection_prefix}bundle:"

    if identifier.startswith(bundle_prefix):
        local_identifier = identifier[len(bundle_prefix):]
        if local_identifier:
            return ParsedOAIIdentifier(kind="bundle", local_identifier=local_identifier)
        return None

    if identifier.startswith(collection_prefix):
        local_identifier = identifier[len(collection_prefix):]
        if local_identifier and not local_identifier.startswith("bundle:"):
            return ParsedOAIIdentifier(
                kind="collection",
                local_identifier=local_identifier,
            )

    return None
