from django.http import HttpResponsePermanentRedirect
from django.urls import reverse


def _permanent_canonical_redirect(request, view_name: str, **kwargs):
    location = reverse(view_name, kwargs=kwargs)
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        location = f"{location}?{query_string}"
    return HttpResponsePermanentRedirect(location)


def legacy_collection_by_handle(request, handle_id):
    return _permanent_canonical_redirect(
        request,
        "explorer:collection_detail_by_handle",
        handle=handle_id,
    )


def legacy_bundle_by_handle(request, handle_id):
    return _permanent_canonical_redirect(
        request,
        "explorer:bundle_detail_by_handle",
        handle=handle_id,
    )
