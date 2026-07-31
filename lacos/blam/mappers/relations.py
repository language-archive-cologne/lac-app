"""Small helpers for prefetch-friendly relation access in mappers."""

from __future__ import annotations


def first_of(relation):
    """Return the first related object without bypassing the prefetch cache.

    ``relation.first()`` always issues a fresh query; iterating ``.all()``
    reuses ``prefetch_related`` results when they exist.
    """

    return next(iter(relation.all()), None)
