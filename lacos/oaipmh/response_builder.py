"""Utility helpers to build OAI-PMH XML responses."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from django.http import HttpRequest, HttpResponse

from .constants import (
    REPO_ADMIN_EMAIL,
    REPO_BASE_ENDPOINT,
    REPO_EARLIEST_DATASTAMP,
    REPO_GRANULARITY,
    REPO_IDENTIFIER,
    REPO_NAME,
    REPO_OAI_DELIMITER,
    REPO_OAI_SCHEME,
    REPO_PROTOCOL_VERSION,
    REPO_SAMPLE_IDENTIFIER,
)
from .errors import OAIPMHError, normalize_errors

OAI_NS = "http://www.openarchives.org/OAI/2.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
OAI_IDENTIFIER_NS = "http://www.openarchives.org/OAI/2.0/oai-identifier"
DEFAULT_SCHEMA_LOCATION = (
    "http://www.openarchives.org/OAI/2.0/"
    " http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd"
)

# Register namespace prefixes for ElementTree serialization
ET.register_namespace("", OAI_NS)
ET.register_namespace("xsi", XSI_NS)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _base_request_element(oai_request_uri: str, verb: str) -> ET.Element:
    element = ET.Element("request")
    element.text = oai_request_uri
    element.set("verb", verb)
    return element


def _build_envelope(request: HttpRequest, verb: str) -> ET.Element:
    envelope = ET.Element("{%s}OAI-PMH" % OAI_NS)
    envelope.set("xmlns:xsi", XSI_NS)
    envelope.set("xsi:schemaLocation", DEFAULT_SCHEMA_LOCATION)
    response_date = ET.SubElement(envelope, "responseDate")
    response_date.text = _now_utc()
    base_uri = request.build_absolute_uri(REPO_BASE_ENDPOINT)
    envelope.append(_base_request_element(base_uri, verb))
    return envelope


def render_error_response(request: HttpRequest, verb: str, errors: Iterable[OAIPMHError]) -> HttpResponse:
    envelope = _build_envelope(request, verb)
    for error in normalize_errors(errors):
        error_el = ET.SubElement(envelope, "error")
        error_el.set("code", error.code)
        error_el.text = error.message
    return _as_http_response(envelope)


def render_identify(request: HttpRequest) -> HttpResponse:
    envelope = _build_envelope(request, "Identify")
    identify = ET.SubElement(envelope, "Identify")
    ET.SubElement(identify, "repositoryName").text = REPO_NAME
    ET.SubElement(identify, "baseURL").text = request.build_absolute_uri(REPO_BASE_ENDPOINT)
    ET.SubElement(identify, "protocolVersion").text = REPO_PROTOCOL_VERSION
    ET.SubElement(identify, "adminEmail").text = REPO_ADMIN_EMAIL
    ET.SubElement(identify, "earliestDatestamp").text = REPO_EARLIEST_DATASTAMP
    ET.SubElement(identify, "deletedRecord").text = "no"
    ET.SubElement(identify, "granularity").text = REPO_GRANULARITY
    _append_oai_identifier_description(identify)
    return _as_http_response(envelope)


def _append_oai_identifier_description(identify: ET.Element) -> None:
    """Declare the registered OLAC repository identifier scheme.

    See http://www.openarchives.org/OAI/2.0/guidelines-oai-identifier.htm
    """

    description = ET.SubElement(identify, "description")
    oai_identifier = ET.SubElement(description, "oai-identifier")
    oai_identifier.set("xmlns", OAI_IDENTIFIER_NS)
    oai_identifier.set(
        "xsi:schemaLocation",
        f"{OAI_IDENTIFIER_NS} {OAI_IDENTIFIER_NS}.xsd",
    )
    ET.SubElement(oai_identifier, "scheme").text = REPO_OAI_SCHEME
    ET.SubElement(oai_identifier, "repositoryIdentifier").text = REPO_IDENTIFIER
    ET.SubElement(oai_identifier, "delimiter").text = REPO_OAI_DELIMITER
    ET.SubElement(oai_identifier, "sampleIdentifier").text = REPO_SAMPLE_IDENTIFIER


def render_metadata_formats(request: HttpRequest, formats: Iterable[dict[str, str]]) -> HttpResponse:
    envelope = _build_envelope(request, "ListMetadataFormats")
    container = ET.SubElement(envelope, "ListMetadataFormats")
    for fmt in formats:
        fmt_el = ET.SubElement(container, "metadataFormat")
        ET.SubElement(fmt_el, "metadataPrefix").text = fmt["metadata_prefix"]
        ET.SubElement(fmt_el, "schema").text = fmt["schema"]
        ET.SubElement(fmt_el, "metadataNamespace").text = fmt["namespace"]
    return _as_http_response(envelope)


def render_empty_list(request: HttpRequest, verb: str, resumption_token: Optional[str] = None) -> HttpResponse:
    envelope = _build_envelope(request, verb)
    container = ET.SubElement(envelope, verb)
    if resumption_token:
        token_el = ET.SubElement(container, "resumptionToken")
        token_el.text = resumption_token
    return _as_http_response(envelope)


def render_list_identifiers(
    request: HttpRequest,
    headers: Iterable[dict],
    resumption_token: Optional[str] = None,
) -> HttpResponse:
    envelope = _build_envelope(request, "ListIdentifiers")
    container = ET.SubElement(envelope, "ListIdentifiers")
    for header in headers:
        header_el = ET.SubElement(container, "header")
        ET.SubElement(header_el, "identifier").text = header["identifier"]
        ET.SubElement(header_el, "datestamp").text = header["datestamp"]
        for set_spec in header.get("sets", []):
            ET.SubElement(header_el, "setSpec").text = set_spec
    if resumption_token:
        token_el = ET.SubElement(container, "resumptionToken")
        token_el.text = resumption_token
    return _as_http_response(envelope)


def render_list_records(
    request: HttpRequest,
    records: Iterable[dict],
    resumption_token: Optional[str] = None,
) -> HttpResponse:
    # Check if any metadata is a string (needs string-based response building)
    records_list = list(records)
    has_string_metadata = any(isinstance(r.get("metadata"), str) for r in records_list)

    if has_string_metadata:
        return _render_list_records_with_string_metadata(request, records_list, resumption_token)

    # Standard ElementTree-based approach for Element metadata
    envelope = _build_envelope(request, "ListRecords")
    container = ET.SubElement(envelope, "ListRecords")
    for record in records_list:
        record_el = ET.SubElement(container, "record")
        header_el = ET.SubElement(record_el, "header")
        ET.SubElement(header_el, "identifier").text = record["identifier"]
        ET.SubElement(header_el, "datestamp").text = record["datestamp"]
        for set_spec in record.get("sets", []):
            ET.SubElement(header_el, "setSpec").text = set_spec
        metadata_el = ET.SubElement(record_el, "metadata")
        metadata_el.append(record["metadata"])
    if resumption_token:
        token_el = ET.SubElement(container, "resumptionToken")
        token_el.text = resumption_token
    return _as_http_response(envelope)


def render_get_record(request: HttpRequest, record: dict) -> HttpResponse:
    metadata = record["metadata"]
    if isinstance(metadata, str):
        return _render_get_record_with_string_metadata(request, record)

    envelope = _build_envelope(request, "GetRecord")
    container = ET.SubElement(envelope, "GetRecord")
    record_el = ET.SubElement(container, "record")
    header_el = ET.SubElement(record_el, "header")
    ET.SubElement(header_el, "identifier").text = record["identifier"]
    ET.SubElement(header_el, "datestamp").text = record["datestamp"]
    for set_spec in record.get("sets", []):
        ET.SubElement(header_el, "setSpec").text = set_spec
    metadata_el = ET.SubElement(record_el, "metadata")
    metadata_el.append(metadata)
    return _as_http_response(envelope)


def _render_get_record_with_string_metadata(
    request: HttpRequest,
    record: dict,
) -> HttpResponse:
    """Build GetRecord response preserving metadata XML namespace declarations."""

    base_uri = request.build_absolute_uri(REPO_BASE_ENDPOINT)
    response_date = _now_utc()
    set_specs = "".join(
        f"<setSpec>{_escape_xml(s)}</setSpec>"
        for s in record.get("sets", [])
    )
    metadata = record["metadata"]
    if isinstance(metadata, ET.Element):
        metadata = ET.tostring(metadata, encoding="unicode")

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<OAI-PMH xmlns="{OAI_NS}" xmlns:xsi="{XSI_NS}" '
        f'xsi:schemaLocation="{DEFAULT_SCHEMA_LOCATION}">'
        f'<responseDate>{response_date}</responseDate>'
        f'<request verb="GetRecord">{_escape_xml(base_uri)}</request>'
        f'<GetRecord><record><header>'
        f'<identifier>{_escape_xml(record["identifier"])}</identifier>'
        f'<datestamp>{record["datestamp"]}</datestamp>'
        f'{set_specs}'
        f'</header><metadata>{metadata}</metadata></record></GetRecord>'
        f'</OAI-PMH>'
    )
    return HttpResponse(xml.encode("utf-8"), content_type="text/xml; charset=utf-8")


def _render_list_records_with_string_metadata(
    request: HttpRequest,
    records: list[dict],
    resumption_token: Optional[str] = None,
) -> HttpResponse:
    """Build ListRecords response preserving metadata XML namespace declarations."""
    base_uri = request.build_absolute_uri(REPO_BASE_ENDPOINT)
    response_date = _now_utc()

    records_xml = []
    for record in records:
        set_specs = "".join(f"<setSpec>{s}</setSpec>" for s in record.get("sets", []))
        metadata = record["metadata"]
        if isinstance(metadata, ET.Element):
            metadata = ET.tostring(metadata, encoding="unicode")

        records_xml.append(
            f'<record><header>'
            f'<identifier>{_escape_xml(record["identifier"])}</identifier>'
            f'<datestamp>{record["datestamp"]}</datestamp>'
            f'{set_specs}'
            f'</header><metadata>{metadata}</metadata></record>'
        )

    token_xml = ""
    if resumption_token:
        token_xml = f"<resumptionToken>{_escape_xml(resumption_token)}</resumptionToken>"

    xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<OAI-PMH xmlns="{OAI_NS}" xmlns:xsi="{XSI_NS}" '
        f'xsi:schemaLocation="{DEFAULT_SCHEMA_LOCATION}">'
        f'<responseDate>{response_date}</responseDate>'
        f'<request verb="ListRecords">{_escape_xml(base_uri)}</request>'
        f'<ListRecords>{"".join(records_xml)}{token_xml}</ListRecords>'
        f'</OAI-PMH>'
    )
    return HttpResponse(xml.encode("utf-8"), content_type="text/xml; charset=utf-8")


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_list_sets(request: HttpRequest, sets: Iterable[dict[str, str]]) -> HttpResponse:
    envelope = _build_envelope(request, "ListSets")
    container = ET.SubElement(envelope, "ListSets")
    for item in sets:
        set_el = ET.SubElement(container, "set")
        ET.SubElement(set_el, "setSpec").text = item["spec"]
        ET.SubElement(set_el, "setName").text = item["name"]
    return _as_http_response(envelope)


def _as_http_response(envelope: ET.Element) -> HttpResponse:
    xml_bytes = ET.tostring(envelope, encoding="utf-8")
    return HttpResponse(xml_bytes, content_type="text/xml; charset=utf-8")
