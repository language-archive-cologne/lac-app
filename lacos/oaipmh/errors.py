"""OAI-PMH specific exceptions and error helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class OAIPMHError(Exception):
    code: str
    message: str

    def as_tuple(self) -> tuple[str, str]:
        return self.code, self.message


def normalize_errors(errors: Iterable[OAIPMHError]) -> List[OAIPMHError]:
    return [error if isinstance(error, OAIPMHError) else OAIPMHError("badArgument", str(error)) for error in errors]
