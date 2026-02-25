"""Views for the IMDI metadata browser."""

import json
import logging
from posixpath import dirname
from posixpath import join as posix_join

from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from django.views import View

from lacos.blam.models import Collection
from lacos.explorer.services.imdi_parser import ImdiNode
from lacos.explorer.services.imdi_parser import parse_imdi
from lacos.explorer.services.imdi_storage import ImdiStorageService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

logger = logging.getLogger(__name__)

MISSING_COLLECTION_BUCKET = "Collection has no import bucket configured."
NO_IMDI_FILES = "No IMDI files found for this collection."
NO_ROOT_IMDI = "No root IMDI file found for this collection."
ROOT_READ_FAILURE = "Could not read root IMDI file."
ROOT_PARSE_FAILURE = "Could not parse root IMDI file."
MISSING_BUCKET_OR_KEY = "Missing bucket or key parameter."
READ_FAILURE = "Could not read IMDI file."
PARSE_FAILURE = "Could not parse IMDI file."
INVALID_CHILD_INDEX = "Invalid child index."


def _raise_not_found(message: str) -> None:
    raise Http404(message)


def _get_storage_service() -> ImdiStorageService:
    """Create an ``ImdiStorageService`` backed by the app S3 client."""
    resource_service = ResourceMappingService(skip_bucket_check=True)
    return ImdiStorageService(s3_client=resource_service.s3_client)


def _normalize_prefix(prefix: str) -> str:
    """Normalize an object key to a directory-like prefix."""
    if not prefix:
        return ""
    if prefix.endswith("/"):
        return prefix
    directory = dirname(prefix)
    if not directory:
        return ""
    return f"{directory}/"


def _resolve_child_corpus_links(node: ImdiNode, key: str) -> None:
    """Resolve immediate child corpus links against the current key's directory."""
    base_dir = dirname(key)
    for child in node.children:
        if child.corpus_link:
            child.resolved_key = posix_join(base_dir, child.corpus_link)


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

        xml_bytes = storage.read_imdi_file(bucket, root_key)
        if not xml_bytes:
            _raise_not_found(ROOT_READ_FAILURE)

        root_node = parse_imdi(xml_bytes)
        if not root_node:
            _raise_not_found(ROOT_PARSE_FAILURE)

        _resolve_child_corpus_links(root_node, root_key)

        if is_htmx:
            template_name = "explorer/imdi/partials/modal_content.html"
        else:
            template_name = "explorer/imdi_browser.html"
        response = render(
            request,
            template_name,
            {
                "collection": collection,
                "root_node": root_node,
                "bucket": bucket,
                "root_key": root_key,
            },
        )
        if is_htmx:
            response["HX-Trigger"] = json.dumps({"showResourceModal": True})
        return response


class ImdiTreeChildrenView(View):
    """htmx endpoint: return child nodes for tree expansion."""

    def get(self, request: HttpRequest) -> HttpResponse:
        bucket = request.GET.get("bucket", "")
        key = request.GET.get("key", "")

        if not bucket or not key:
            _raise_not_found(MISSING_BUCKET_OR_KEY)

        storage = _get_storage_service()
        xml_bytes = storage.read_imdi_file(bucket, key)
        if not xml_bytes:
            _raise_not_found(READ_FAILURE)

        node = parse_imdi(xml_bytes)
        if not node:
            _raise_not_found(PARSE_FAILURE)

        _resolve_child_corpus_links(node, key)

        return render(
            request,
            "explorer/imdi/partials/tree_children.html",
            {
                "node": node,
                "bucket": bucket,
                "parent_key": key,
            },
        )


class ImdiDetailView(View):
    """htmx endpoint: return metadata panel for a selected node."""

    def get(self, request: HttpRequest) -> HttpResponse:
        bucket = request.GET.get("bucket", "")
        key = request.GET.get("key", "")
        child_index = request.GET.get("child")

        if not bucket or not key:
            _raise_not_found(MISSING_BUCKET_OR_KEY)

        storage = _get_storage_service()
        xml_bytes = storage.read_imdi_file(bucket, key)
        if not xml_bytes:
            _raise_not_found(READ_FAILURE)

        node = parse_imdi(xml_bytes)
        if not node:
            _raise_not_found(PARSE_FAILURE)

        if child_index is not None:
            try:
                node = node.children[int(child_index)]
            except (ValueError, IndexError) as exc:
                raise Http404(INVALID_CHILD_INDEX) from exc

        return render(
            request,
            "explorer/imdi/partials/metadata_panel.html",
            {
                "node": node,
                "bucket": bucket,
                "key": key,
            },
        )
