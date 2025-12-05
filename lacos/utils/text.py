"""
Text normalization utilities.
"""
from __future__ import annotations

import unicodedata
from typing import TypeVar

T = TypeVar("T", bound=str | None)


def normalize_nfc(text: T) -> T:
    """
    Normalize a string to Unicode NFC form.

    NFC (Canonical Decomposition, followed by Canonical Composition) ensures
    consistent representation of characters. For example, 'u' + combining umlaut
    becomes a single 'ü' character.

    Args:
        text: The string to normalize, or None.

    Returns:
        The NFC-normalized string, or None if input was None.
    """
    if text is None:
        return None  # type: ignore[return-value]
    return unicodedata.normalize("NFC", text)


def normalize_nfc_strip(text: str | None) -> str | None:
    """
    Normalize a string to NFC and strip whitespace.

    Args:
        text: The string to normalize, or None.

    Returns:
        The NFC-normalized and stripped string, or None if input was None or empty.
    """
    if text is None:
        return None
    result = unicodedata.normalize("NFC", text).strip()
    return result if result else None
