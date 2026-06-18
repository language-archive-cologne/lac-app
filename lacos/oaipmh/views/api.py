"""Entry point for the LACOS OAI-PMH endpoint."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import HttpRequest, HttpResponse
from django.utils.dateparse import parse_date, parse_datetime

from ..constants import SUPPORTED_METADATA_FORMATS, SUPPORTED_SETS, DEFAULT_PAGE_SIZE
from ..errors import OAIPMHError
from ..formats import serialize as serialize_metadata
from ..identifiers import parse_oai_identifier
from ..request_parser import OAIRequestParser
from ..resumption import ResumptionTokenService
from ..response_builder import (
    render_error_response,
    render_get_record,
    render_identify,
    render_metadata_formats,
    render_list_identifiers,
    render_list_records,
    render_list_sets,
)
from ..services import (
    fetch_bundle_record_by_identifier,
    fetch_bundle_records,
    fetch_collection_record_by_identifier,
    fetch_collection_records,
    fetch_repository_records,
)

logger = logging.getLogger(__name__)

_resumption = ResumptionTokenService(page_size=DEFAULT_PAGE_SIZE)
SUPPORTED_PREFIXES = {entry["metadata_prefix"] for entry in SUPPORTED_METADATA_FORMATS}


@csrf_exempt
@require_http_methods(["GET", "POST"])
def oai_endpoint(request: HttpRequest) -> HttpResponse:
    try:
        oai_request = OAIRequestParser.parse(request)
    except OAIPMHError as exc:
        return render_error_response(request, "Identify", [exc])

    verb = oai_request.verb
    logger.debug("OAI request", extra={"verb": verb, "params": request.GET.dict()})

    if verb == "Identify":
        return render_identify(request)
    if verb == "ListMetadataFormats":
        return render_metadata_formats(request, SUPPORTED_METADATA_FORMATS)
    if verb in {"ListRecords", "ListIdentifiers"}:
        return _handle_list_verbs(request, verb, oai_request)
    if verb == "ListSets":
        set_items = [
            {"spec": spec, "name": name}
            for spec, name in SUPPORTED_SETS.items()
        ]
        return render_list_sets(request, set_items)
    if verb == "GetRecord":
        return _handle_get_record(request, oai_request)

    return render_error_response(
        request,
        verb,
        [OAIPMHError("badVerb", f"Unsupported verb: {verb}")],
    )


def _handle_get_record(request: HttpRequest, oai_request) -> HttpResponse:
    metadata_prefix = oai_request.metadata_prefix
    identifier = oai_request.identifier

    if not metadata_prefix:
        return render_error_response(
            request,
            "GetRecord",
            [OAIPMHError("badArgument", "metadataPrefix is required")],
        )

    if metadata_prefix not in SUPPORTED_PREFIXES:
        return render_error_response(
            request,
            "GetRecord",
            [
                OAIPMHError(
                    "cannotDisseminateFormat",
                    f"Unsupported metadataPrefix '{metadata_prefix}'",
                )
            ],
        )

    if not identifier:
        return render_error_response(
            request,
            "GetRecord",
            [OAIPMHError("badArgument", "identifier is required")],
        )

    local_identifier = parse_oai_identifier(identifier)
    if local_identifier is None:
        return render_error_response(
            request,
            "GetRecord",
            [OAIPMHError("idDoesNotExist", "Unknown identifier")],
        )

    # Collections and bundles share a single Handle namespace, so the kind is
    # resolved by lookup: try a bundle first, then fall back to a collection.
    user = getattr(request, "user", None)
    record = fetch_bundle_record_by_identifier(
        local_identifier, user=user
    ) or fetch_collection_record_by_identifier(local_identifier, user=user)
    if record is None:
        return render_error_response(
            request,
            "GetRecord",
            [OAIPMHError("idDoesNotExist", "Unknown identifier")],
        )

    metadata_element = serialize_metadata(metadata_prefix, record.metadata)
    return render_get_record(
        request,
        {
            "identifier": record.identifier,
            "datestamp": record.datestamp,
            "sets": record.sets,
            "metadata": metadata_element,
        },
    )


def _handle_list_verbs(request: HttpRequest, verb: str, oai_request) -> HttpResponse:
    metadata_prefix = oai_request.metadata_prefix
    offset = 0
    from_param = oai_request.from_date
    until_param = oai_request.until_date
    set_param = oai_request.set_spec

    if oai_request.resumption_token:
        ok, token_data, error = _resumption.parse_token(oai_request.resumption_token)
        if not ok or token_data is None:
            return render_error_response(request, verb, [OAIPMHError("badResumptionToken", error or "Invalid token")])
        metadata_prefix = token_data.metadata_prefix
        offset = token_data.offset
        from_param = token_data.raw.get("from")
        until_param = token_data.raw.get("until")
        set_param = token_data.raw.get("set")

    if not metadata_prefix:
        return render_error_response(request, verb, [OAIPMHError("badArgument", "metadataPrefix is required")])

    if metadata_prefix not in SUPPORTED_PREFIXES:
        return render_error_response(
            request,
            verb,
            [OAIPMHError("cannotDisseminateFormat", f"Unsupported metadataPrefix '{metadata_prefix}'")],
        )

    if set_param and set_param not in SUPPORTED_SETS:
        return render_error_response(
            request,
            verb,
            [OAIPMHError("badArgument", f"Unsupported set specification '{set_param}'")],
        )

    active_set = set_param

    logger.debug(
        "List verb requested",
        extra={
            "verb": verb,
            "prefix": metadata_prefix,
            "offset": offset,
            "from": from_param,
            "until": until_param,
            "set": active_set or "all",
        },
    )

    from_date = _parse_date_param(from_param)
    until_date = _parse_date_param(until_param)
    page_size = _resumption.page_size

    if active_set == "bundles":
        fetch_fn = fetch_bundle_records
    elif active_set == "collections":
        fetch_fn = fetch_collection_records
    else:
        fetch_fn = fetch_repository_records

    records, has_more = fetch_fn(
        offset=offset,
        from_date=from_date,
        until_date=until_date,
        limit=page_size,
        user=getattr(request, "user", None),
    )

    if not records:
        return render_error_response(request, verb, [OAIPMHError("noRecordsMatch", "No records available for the supplied parameters")])

    next_token = None
    if has_more:
        next_token = _resumption.create_token(
            offset=offset + page_size,
            verb=verb,
            metadata_prefix=metadata_prefix,
            from_date=from_param,
            until_date=until_param,
            set_spec=active_set,
        )

    if verb == "ListIdentifiers":
        headers_payload = [
            {
                "identifier": record.identifier,
                "datestamp": record.datestamp,
                "sets": record.sets,
            }
            for record in records
        ]
        return render_list_identifiers(request, headers_payload, next_token)

    record_payload = []
    for record in records:
        metadata_element = serialize_metadata(metadata_prefix, record.metadata)
        record_payload.append(
            {
                "identifier": record.identifier,
                "datestamp": record.datestamp,
                "sets": record.sets,
                "metadata": metadata_element,
            }
        )

    return render_list_records(request, record_payload, next_token)


def _parse_date_param(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is not None:
        return dt.date()
    return parse_date(value)
