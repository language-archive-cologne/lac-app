"""Shared service utilities for OAI-PMH record assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, MutableMapping

from django.utils import timezone


class RecordMetadata(Mapping[str, object]):
    """Immutable mapping storing flattened metadata key/value pairs."""

    def __init__(self, data: MutableMapping[str, object]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> object:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default=None):
        return self._data.get(key, default)


@dataclass
class OAIRecord:
    identifier: str
    datestamp: str
    metadata: RecordMetadata
    sets: Iterable[str]


def format_timestamp(value: datetime) -> str:
    """Return the timestamp formatted as UTC ISO string."""

    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_default_timezone())
    value_utc = value.astimezone(timezone.utc)
    return value_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
