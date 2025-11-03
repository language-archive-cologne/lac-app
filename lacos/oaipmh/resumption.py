"""Resumption token helpers for OAI-PMH pagination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, unquote

from django.conf import settings


@dataclass(frozen=True)
class ParsedToken:
    """Structured representation of a resumption token payload."""

    offset: int
    verb: str
    metadata_prefix: str
    page_size: int
    raw: Dict[str, Any]


class ResumptionTokenService:
    """Stateless resumption token service using HMAC signatures."""

    def __init__(self, secret_key: Optional[str] = None, page_size: int = 100):
        self.secret_key = secret_key or getattr(settings, "SECRET_KEY", "lacos-oai-default")
        self.page_size = page_size

    # ------------------------------------------------------------------
    # Encoding helpers
    # ------------------------------------------------------------------
    def create_token(
        self,
        *,
        offset: int,
        verb: str,
        metadata_prefix: str,
        set_spec: Optional[str] = None,
        from_date: Optional[str] = None,
        until_date: Optional[str] = None,
        total_count: Optional[int] = None,
    ) -> str:
        payload: Dict[str, Any] = {
            "offset": offset,
            "verb": verb,
            "metadata_prefix": metadata_prefix,
            "page_size": self.page_size,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if set_spec:
            payload["set"] = set_spec
        if from_date:
            payload["from"] = from_date
        if until_date:
            payload["until"] = until_date
        if total_count is not None:
            payload["total_count"] = total_count

        token_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        signature = hmac.new(self.secret_key.encode("utf-8"), token_bytes, hashlib.sha256).hexdigest()
        signed_token = f"{base64.b64encode(token_bytes).decode('ascii')}:{signature}"
        return quote(signed_token)

    # ------------------------------------------------------------------
    # Decoding helpers
    # ------------------------------------------------------------------
    def parse_token(self, token: str) -> Tuple[bool, Optional[ParsedToken], Optional[str]]:
        try:
            unquoted = unquote(token)
            if ":" not in unquoted:
                return False, None, "invalid token format"
            payload_part, signature = unquoted.rsplit(":", 1)
            try:
                payload_bytes = base64.b64decode(payload_part.encode("ascii"))
            except Exception:
                return False, None, "invalid token encoding"

            expected_signature = hmac.new(
                self.secret_key.encode("utf-8"),
                payload_bytes,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected_signature):
                return False, None, "invalid token signature"

            try:
                payload = json.loads(payload_bytes.decode("utf-8"))
            except Exception:
                return False, None, "invalid token payload"

            for field in ("offset", "verb", "metadata_prefix", "page_size"):
                if field not in payload:
                    return False, None, f"missing field: {field}"

            parsed = ParsedToken(
                offset=int(payload["offset"]),
                verb=str(payload["verb"]),
                metadata_prefix=str(payload["metadata_prefix"]),
                page_size=int(payload["page_size"]),
                raw=payload,
            )
            return True, parsed, None
        except Exception as exc:  # pragma: no cover - defensive
            return False, None, str(exc)

    # ------------------------------------------------------------------
    @staticmethod
    def next_offset(token: ParsedToken) -> int:
        return token.offset + token.page_size

    @staticmethod
    def has_more(total_fetched: int, page_size: int) -> bool:
        return total_fetched == page_size
