"""Canonical public search index schema and integrity validation."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

PUBLIC_SEARCH_SCHEMA_VERSION = 1


class PublicSearchSchemaError(ValueError):
    """Raised when an index does not satisfy the public search schema."""


def canonical_index_bytes(index: dict[str, Any], *, include_version: bool) -> bytes:
    content = dict(index)
    if not include_version:
        content.pop("version", None)
    return json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def calculate_index_version(index: dict[str, Any]) -> str:
    return sha256(canonical_index_bytes(index, include_version=False)).hexdigest()


def finalize_public_search_index(index: dict[str, Any]) -> dict[str, Any]:
    finalized = {
        "schema_version": PUBLIC_SEARCH_SCHEMA_VERSION,
        "collections": list(index.get("collections", [])),
        "bundles": list(index.get("bundles", [])),
    }
    finalized["version"] = calculate_index_version(finalized)
    return finalized


def validate_public_search_index(index: object) -> dict[str, Any]:
    if not isinstance(index, dict):
        message = "Public search index must be a JSON object"
        raise TypeError(message)
    if index.get("schema_version") != PUBLIC_SEARCH_SCHEMA_VERSION:
        message = "Public search index schema version is unsupported"
        raise PublicSearchSchemaError(message)
    if not isinstance(index.get("collections"), list) or not isinstance(
        index.get("bundles"),
        list,
    ):
        message = "Public search index record lists are invalid"
        raise TypeError(message)
    expected = calculate_index_version(index)
    if index.get("version") != expected:
        message = "Public search index integrity check failed"
        raise PublicSearchSchemaError(message)
    return index
