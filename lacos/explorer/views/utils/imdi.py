"""Helpers for rendering IMDI resources in explorer modals."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import render

from lacos.explorer.services.imdi_storage import ImdiStorageService

logger = logging.getLogger(__name__)


def is_imdi_resource(file_name: str | None, mime_type: str | None = None) -> bool:
    """Return ``True`` when the resource should be treated as an IMDI file."""
    suffix = Path(file_name or "").suffix.lower()
    if suffix == ".imdi":
        return True
    normalized_mime = (mime_type or "").strip().lower()
    return normalized_mime == "application/x-imdi+xml"


def render_imdi_modal_response(
    request: HttpRequest,
    *,
    s3_client: Any,
    bucket: str,
    key: str,
    collection: Any = None,
) -> HttpResponse | None:
    """Render IMDI modal content for a specific S3 object key.

    Returns ``None`` when the IMDI file cannot be loaded.
    """
    if not s3_client:
        return None

    storage = ImdiStorageService(s3_client=s3_client)
    xml_bytes = storage.read_imdi_file(bucket, key)
    if not xml_bytes:
        logger.warning("Could not read IMDI file for modal: s3://%s/%s", bucket, key)
        return None

    response = render(
        request,
        "explorer/imdi/partials/modal_content.html",
        {
            "collection": collection,
            "bucket": bucket,
            "root_key": key,
        },
    )
    response["HX-Trigger"] = json.dumps({"showResourceModal": True})
    return response
