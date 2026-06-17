"""Helpers for building and parsing LACOS OAI-PMH identifiers.

OAI identifiers follow the OLAC repository convention

    oai:<repositoryIdentifier>:<local-identifier>

where ``repositoryIdentifier`` is the registered ``lac.uni-koeln.de`` and
``local-identifier`` is the bare Handle (prefix/suffix) without the ``hdl:``
scheme. The reserved ``:`` delimiter is therefore only used between the three
top-level components, keeping the local identifier free of reserved characters
apart from the ``/`` that separates Handle prefix and suffix.
"""

from __future__ import annotations

from .constants import REPO_IDENTIFIER

# Scheme prefix used on the stored Collection/Bundle ``identifier`` values.
HANDLE_SCHEME_PREFIX = "hdl:"

_OAI_PREFIX = f"oai:{REPO_IDENTIFIER}:"


def _strip_handle_scheme(record_identifier: str) -> str:
    if record_identifier.startswith(HANDLE_SCHEME_PREFIX):
        return record_identifier[len(HANDLE_SCHEME_PREFIX):]
    return record_identifier


def build_oai_identifier(record_identifier: str) -> str:
    """Return the OLAC OAI identifier for a collection or bundle.

    ``record_identifier`` is the stored Handle (e.g. ``hdl:11341/...``); the
    returned value drops the ``hdl:`` scheme so the local component is the bare
    Handle, e.g. ``oai:lac.uni-koeln.de:11341/...``.
    """

    return f"{_OAI_PREFIX}{_strip_handle_scheme(record_identifier)}"


def parse_oai_identifier(identifier: str | None) -> str | None:
    """Return the stored record identifier encoded in an OAI identifier.

    Inverse of :func:`build_oai_identifier`: re-attaches the ``hdl:`` scheme so
    the result matches the ``identifier`` column on Collection/Bundle. Returns
    ``None`` for identifiers that do not belong to this repository. Collections
    and bundles share a single Handle namespace, so the record kind is resolved
    by lookup rather than encoded in the identifier.
    """

    if not identifier or not identifier.startswith(_OAI_PREFIX):
        return None

    local = identifier[len(_OAI_PREFIX):]
    if not local:
        return None

    return f"{HANDLE_SCHEME_PREFIX}{local}"
