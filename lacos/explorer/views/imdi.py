"""Views for the IMDI metadata browser."""

import logging

from django.http import Http404
from django.http import HttpRequest
from django.http import HttpResponse
from django.views import View

from lacos.explorer.services.imdi_storage import ImdiStorageService
from lacos.storage.services.resource_mapping_service import ResourceMappingService

logger = logging.getLogger(__name__)

READ_FAILURE = "Could not read IMDI file."


def _get_storage_service() -> ImdiStorageService:
    """Create an ``ImdiStorageService`` backed by the app S3 client."""
    resource_service = ResourceMappingService(skip_bucket_check=True)
    return ImdiStorageService(s3_client=resource_service.s3_client)


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
