"""Atomic persistence and validated loading for the public search index."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import Any

from lacos.explorer.public_search.schema import canonical_index_bytes
from lacos.explorer.public_search.schema import finalize_public_search_index
from lacos.explorer.public_search.schema import validate_public_search_index


class PublicSearchIndexError(RuntimeError):
    """Raised when a public search index cannot be loaded safely."""

    def __init__(self, error: BaseException):
        super().__init__(f"Unable to load public search index: {error}")


def write_public_search_index(
    path: str | os.PathLike[str],
    index: dict[str, Any],
) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    finalized = finalize_public_search_index(index)
    payload = canonical_index_bytes(finalized, include_version=True)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(0o644)
        temporary_path.replace(target)
    except BaseException:
        with suppress(FileNotFoundError):
            temporary_path.unlink()
        raise

    clear_public_search_index_cache()
    return finalized["version"]


def load_public_search_index(path: str | os.PathLike[str]) -> dict[str, Any]:
    target = Path(path)
    try:
        stat = target.stat()
        return _load_cached(str(target.resolve()), stat.st_mtime_ns, stat.st_size)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise PublicSearchIndexError(error) from error


@lru_cache(maxsize=4)
def _load_cached(path: str, modified_ns: int, size: int) -> dict[str, Any]:
    del modified_ns, size
    with Path(path).open("r", encoding="utf-8") as source:
        loaded = json.load(source)
    return validate_public_search_index(loaded)


def clear_public_search_index_cache() -> None:
    _load_cached.cache_clear()
