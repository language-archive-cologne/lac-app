"""Validation and diagnostic context for Explorer resource actions."""

from __future__ import annotations

import logging
from typing import Any

from django.http import Http404

from lacos.common.request_utils import get_client_ip

logger = logging.getLogger(__name__)

SUPPORTED_RESOURCE_ACTIONS = frozenset({"analyze", "pitch", "play", "view"})
MAX_LOGGED_ACTION_LENGTH = 128
UNSUPPORTED_ACTION_MESSAGE = "Unsupported action"


def ensure_supported_resource_action(
    request,
    *,
    action: str,
    container: Any,
    resource: Any,
) -> None:
    """Reject unsupported presentation actions with bounded structured logging."""
    if action in SUPPORTED_RESOURCE_ACTIONS:
        return

    logger.warning(
        "Unsupported resource action",
        extra=resource_request_log_context(
            request,
            action=action,
            container=container,
            resource=resource,
        ),
    )
    raise Http404(UNSUPPORTED_ACTION_MESSAGE)


def resource_request_log_context(
    request,
    *,
    action: str,
    container: Any,
    resource: Any,
) -> dict[str, Any]:
    """Build safe, structured context for resource-access diagnostics."""
    user = getattr(request, "user", None)
    return {
        "resource_action": action[:MAX_LOGGED_ACTION_LENGTH],
        "resource_action_length": len(action),
        "request_path": getattr(request, "path", ""),
        "client_ip": get_client_ip(request),
        "authenticated": bool(getattr(user, "is_authenticated", False)),
        "user_id": _string_identifier(getattr(user, "pk", None)),
        "resource_model": _model_label(resource),
        "resource_id": _string_identifier(getattr(resource, "pk", None)),
        "resource_pid": str(getattr(resource, "file_pid", "") or ""),
        "container_model": _model_label(container),
        "container_id": _string_identifier(getattr(container, "pk", None)),
        "container_identifier": str(getattr(container, "identifier", "") or ""),
    }


def _model_label(instance: Any) -> str:
    meta = getattr(instance, "_meta", None)
    return str(getattr(meta, "label_lower", instance.__class__.__name__))


def _string_identifier(value: Any) -> str:
    return "" if value is None else str(value)
