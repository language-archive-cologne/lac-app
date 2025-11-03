"""Core mapping primitives for metadata serialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional


ValueResolver = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class FieldMap:
    """Describe how to produce one or more target fields."""

    targets: tuple[str, ...]
    source: Optional[str] = None
    constant: Optional[Any] = None
    transform: Optional[ValueResolver] = None
    note: str = ""

    def resolve(self, record: Mapping[str, Any]) -> Iterable[tuple[str, Any]]:
        if self.constant is not None:
            value = self.constant
        elif self.transform is not None:
            value = self.transform(record)
        elif self.source is not None:
            value = record.get(self.source)
        else:
            value = None

        if value is None or value == "":
            return []

        values: Iterable[Any]
        if isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = (value,)

        return [
            (target, item)
            for target in self.targets
            for item in values
            if item is not None and item != ""
        ]
