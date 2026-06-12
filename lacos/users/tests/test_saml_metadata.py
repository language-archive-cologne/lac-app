from __future__ import annotations

import pytest
from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import fromstring

from lacos.users.saml_metadata import MD_NS
from lacos.users.saml_metadata import REQUEST_INIT_NS
from lacos.users.saml_metadata import REQUEST_INITIATOR_BINDING
from lacos.users.saml_metadata import XS_NS
from lacos.users.saml_metadata import add_request_initiator


def test_add_request_initiator_adds_extension_to_sp_metadata():
    metadata = b"""
    <md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata">
      <md:SPSSODescriptor>
        <md:Extensions />
      </md:SPSSODescriptor>
    </md:EntityDescriptor>
    """

    updated = add_request_initiator(
        metadata,
        location="https://lacos.uni-koeln.de/saml2/login/",
    )

    root = fromstring(updated)
    request_initiator = root.find(
        f".//{{{REQUEST_INIT_NS}}}RequestInitiator",
    )
    assert request_initiator is not None
    assert request_initiator.get("Binding") == REQUEST_INITIATOR_BINDING
    assert request_initiator.get("Location") == (
        "https://lacos.uni-koeln.de/saml2/login/"
    )


def test_add_request_initiator_creates_extensions_when_missing():
    metadata = b"""
    <md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata">
      <md:SPSSODescriptor />
    </md:EntityDescriptor>
    """

    updated = add_request_initiator(
        metadata,
        location="https://lacos.uni-koeln.de/saml2/login/",
    )

    root = fromstring(updated)
    extensions = root.find(f".//{{{MD_NS}}}SPSSODescriptor/{{{MD_NS}}}Extensions")
    assert extensions is not None
    assert extensions.find(f"{{{REQUEST_INIT_NS}}}RequestInitiator") is not None


def test_add_request_initiator_does_not_duplicate_existing_element():
    metadata = b"""
    <md:EntityDescriptor
        xmlns:init="urn:oasis:names:tc:SAML:profiles:SSO:request-init"
        xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata">
      <md:SPSSODescriptor>
        <md:Extensions>
          <init:RequestInitiator
              Binding="old-binding"
              Location="https://lacos.uni-koeln.de/saml2/login/" />
        </md:Extensions>
      </md:SPSSODescriptor>
    </md:EntityDescriptor>
    """

    updated = add_request_initiator(
        metadata,
        location="https://lacos.uni-koeln.de/saml2/login/",
    )

    root = fromstring(updated)
    request_initiators = root.findall(
        f".//{{{REQUEST_INIT_NS}}}RequestInitiator",
    )
    assert len(request_initiators) == 1
    assert request_initiators[0].get("Binding") == REQUEST_INITIATOR_BINDING


def test_add_request_initiator_leaves_metadata_unchanged_without_location():
    metadata = b"<metadata />"

    assert add_request_initiator(metadata, location="") == metadata


def test_add_request_initiator_preserves_xs_namespace_for_xsi_type_values():
    metadata = b"""
    <md:EntityDescriptor
        xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
        xmlns:xs="http://www.w3.org/2001/XMLSchema"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <md:Extensions>
        <AttributeValue xsi:type="xs:string">value</AttributeValue>
      </md:Extensions>
      <md:SPSSODescriptor />
    </md:EntityDescriptor>
    """

    updated = add_request_initiator(
        metadata,
        location="https://lacos.uni-koeln.de/saml2/login/",
    )

    assert b'xmlns:xs="' + XS_NS.encode() + b'"' in updated
    assert b'xsi:type="xs:string"' in updated


def test_add_request_initiator_raises_for_invalid_xml():
    with pytest.raises(ParseError):
        add_request_initiator(b"<metadata>", location="https://example.org/login/")
