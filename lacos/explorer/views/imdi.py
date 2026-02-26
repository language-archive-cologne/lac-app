"""Views for the IMDI metadata browser."""

import json
import logging

from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View

from lacos.blam.models import Collection
from lacos.explorer.services.imdi_storage import ImdiStorageService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

logger = logging.getLogger(__name__)

MISSING_COLLECTION_BUCKET = "Collection has no import bucket configured."
NO_IMDI_FILES = "No IMDI files found for this collection."
NO_ROOT_IMDI = "No root IMDI file found for this collection."
READ_FAILURE = "Could not read IMDI file."


def _raise_not_found(message: str) -> None:
    raise Http404(message)


def _get_storage_service() -> ImdiStorageService:
    """Create an ``ImdiStorageService`` backed by the app S3 client."""
    resource_service = ResourceMappingService(skip_bucket_check=True)
    return ImdiStorageService(s3_client=resource_service.s3_client)


def _normalize_prefix(prefix: str) -> str:
    """Normalize an object key to a directory-like prefix."""
    from posixpath import dirname

    if not prefix:
        return ""
    if prefix.endswith("/"):
        return prefix
    directory = dirname(prefix)
    if not directory:
        return ""
    return f"{directory}/"


class ImdiBrowserView(View):
    """Main IMDI browser page for a collection."""

    def get(self, request: HttpRequest, pk) -> HttpResponse:
        is_htmx = request.headers.get("HX-Request") == "true"
        collection = get_object_or_404(Collection, pk=pk)
        bucket = collection.import_bucket
        prefix = _normalize_prefix(collection.import_object_key or "")

        if not bucket:
            _raise_not_found(MISSING_COLLECTION_BUCKET)

        storage = _get_storage_service()
        imdi_keys = storage.discover_imdi_files(bucket, prefix)
        if not imdi_keys:
            _raise_not_found(NO_IMDI_FILES)

        root_key = storage.find_root_imdi(imdi_keys, prefix)
        if not root_key:
            _raise_not_found(NO_ROOT_IMDI)

        if is_htmx:
            template_name = "explorer/imdi/partials/modal_content.html"
        else:
            template_name = "explorer/imdi_browser.html"
        response = render(
            request,
            template_name,
            {
                "collection": collection,
                "bucket": bucket,
                "root_key": root_key,
            },
        )
        if is_htmx:
            response["HX-Trigger"] = json.dumps({"showResourceModal": True})
        return response


class ImdiXmlView(View):
    """Return raw IMDI XML from S3 for client-side rendering."""

    def get(self, request: HttpRequest) -> HttpResponse:
        bucket = request.GET.get("bucket", "")
        key = request.GET.get("key", "")
        if not bucket or not key:
            return HttpResponse(status=400)
        storage = _get_storage_service()
        xml_bytes = storage.read_imdi_file(bucket, key)
        if not xml_bytes:
            raise Http404(READ_FAILURE)
        return HttpResponse(xml_bytes, content_type="application/xml; charset=utf-8")
