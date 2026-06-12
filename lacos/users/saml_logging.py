from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from django.http import HttpRequest

EPPN_ATTRIBUTE_NAMES = (
    "eduPersonPrincipalName",
    "urn:oid:1.3.6.1.4.1.5923.1.1.1.6",
)
MAX_LOG_VALUE_LENGTH = 500


def build_acs_failure_log_context(
    request: HttpRequest,
    *,
    exception: Exception | None,
    status: int,
    session_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attributes = _attributes_from_session(session_info)
    eppn = _first_attribute_value(attributes, EPPN_ATTRIBUTE_NAMES)

    return {
        "saml_failure_exception_type": type(exception).__name__ if exception else "",
        "saml_failure_exception": _safe_text(str(exception)) if exception else "",
        "saml_failure_status": status,
        "saml_failure_issuer": _safe_text(str((session_info or {}).get("issuer", ""))),
        "saml_failure_name_id_present": bool((session_info or {}).get("name_id")),
        "saml_failure_attribute_names": sorted(str(key) for key in attributes),
        "saml_failure_has_eppn": bool(eppn),
        "saml_failure_eppn_scope": _eppn_scope(eppn),
        "saml_failure_has_saml_response": "SAMLResponse" in request.POST,
        "saml_failure_relay_state": _sanitize_relay_state(
            request.POST.get("RelayState", ""),
        ),
        "saml_failure_path": request.path,
        "saml_failure_remote_addr": _client_ip(request),
        "saml_failure_user_agent": _safe_text(
            request.META.get("HTTP_USER_AGENT", ""),
        ),
    }


def _attributes_from_session(
    session_info: dict[str, Any] | None,
) -> dict[str, Any]:
    if not session_info:
        return {}
    attributes = session_info.get("ava") or {}
    if not isinstance(attributes, dict):
        return {}
    return attributes


def _first_attribute_value(
    attributes: dict[str, Any],
    names: tuple[str, ...],
) -> str:
    for name in names:
        value = attributes.get(name)
        first_value = _first_value(value)
        if first_value:
            return first_value
    return ""


def _first_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if item:
                text = str(item).strip()
                if text:
                    return text
        return ""
    return str(value).strip()


def _eppn_scope(eppn: str) -> str:
    if "@" not in eppn:
        return ""
    return eppn.rsplit("@", 1)[1]


def _sanitize_relay_state(relay_state: str) -> str:
    if not relay_state:
        return ""

    parsed = urlsplit(relay_state)
    if parsed.scheme or parsed.netloc:
        return _safe_text(f"{parsed.scheme}://{parsed.netloc}{parsed.path}")
    return _safe_text(parsed.path)


def _client_ip(request: HttpRequest) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _safe_text(value: str) -> str:
    if len(value) <= MAX_LOG_VALUE_LENGTH:
        return value
    return f"{value[:MAX_LOG_VALUE_LENGTH]}...[truncated]"
