from __future__ import annotations

import xml.etree.ElementTree as ET

from defusedxml.ElementTree import fromstring

MD_NS = "urn:oasis:names:tc:SAML:2.0:metadata"
REQUEST_INIT_NS = "urn:oasis:names:tc:SAML:profiles:SSO:request-init"
REQUEST_INITIATOR_BINDING = REQUEST_INIT_NS
XS_NS = "http://www.w3.org/2001/XMLSchema"

ET.register_namespace("md", MD_NS)
ET.register_namespace("init", REQUEST_INIT_NS)


def add_request_initiator(
    metadata_xml: bytes,
    *,
    location: str,
) -> bytes:
    """Add the SAML request-init extension required by CLARIN metadata QA."""
    if not location:
        return metadata_xml

    root = fromstring(metadata_xml)
    for sp_descriptor in root.findall(f".//{{{MD_NS}}}SPSSODescriptor"):
        extensions = sp_descriptor.find(f"{{{MD_NS}}}Extensions")
        if extensions is None:
            extensions = ET.Element(f"{{{MD_NS}}}Extensions")
            sp_descriptor.insert(0, extensions)

        request_initiators = extensions.findall(
            f"{{{REQUEST_INIT_NS}}}RequestInitiator",
        )
        if request_initiators:
            for request_initiator in request_initiators:
                request_initiator.set("Binding", REQUEST_INITIATOR_BINDING)
            continue

        ET.SubElement(
            extensions,
            f"{{{REQUEST_INIT_NS}}}RequestInitiator",
            {
                "Binding": REQUEST_INITIATOR_BINDING,
                "Location": location,
            },
        )

    _ensure_xs_namespace(root)
    return ET.tostring(root, encoding="utf-8")


def _ensure_xs_namespace(root: ET.Element) -> None:
    if any(
        isinstance(value, str) and value.startswith("xs:")
        for element in root.iter()
        for value in element.attrib.values()
    ):
        root.set("xmlns:xs", XS_NS)
