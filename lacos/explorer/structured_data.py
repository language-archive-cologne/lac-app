"""Structured data payloads for public explorer pages."""

import json

CATALOGUE_DESCRIPTION = (
    "The Language Archive Cologne is a digital archive of language resources "
    "containing collections of primary language data, including audio and video "
    "recordings, as well as linguistic analyses."
)

ORGANIZATION_NAME = "Language Archive Cologne"
ORGANIZATION_ALTERNATE_NAME = "LAC"
PERMANENT_ROOT_URL = "https://lac.uni-koeln.de/"
CURRENT_ROOT_URL = "https://lacos.uni-koeln.de/"

# Organisation projection depths. A single serializer keeps the root-page node
# (full institutional genealogy) and the trimmed/minimal nodes nested on
# collection pages in sync (issue #152, design decision 5).
ORG_DEPTH_FULL = "full"
ORG_DEPTH_TRIMMED = "trimmed"
ORG_DEPTH_MINIMAL = "minimal"


def _re3data_identifier() -> dict:
    return {
        "@type": "PropertyValue",
        "propertyID": "re3data",
        "value": "r3d100012786",
        "url": "https://doi.org/10.17616/R3JV4W",
    }


def build_organization_node(root_url: str, depth: str = ORG_DEPTH_FULL) -> dict:
    """Build the LAC ``ArchiveOrganization`` node at one of three projection depths.

    - ``minimal``: ``@type``/``@id``/``name`` only (used for ``sdPublisher``).
    - ``trimmed``: adds ``alternateName``/``url``/re3data ``identifier`` (used
      for ``publisher`` nested on collection pages).
    - ``full``: adds contact, location, certification, genealogy, and membership
      data (used on the catalogue root page only).

    ``root_url`` must already carry its trailing slash.
    """
    organization_id = f"{root_url}#org"
    node = {
        "@type": "ArchiveOrganization",
        "@id": organization_id,
        "name": ORGANIZATION_NAME,
    }
    if depth == ORG_DEPTH_MINIMAL:
        return node

    node["alternateName"] = ORGANIZATION_ALTERNATE_NAME
    node["url"] = root_url
    node["identifier"] = _re3data_identifier()
    if depth == ORG_DEPTH_TRIMMED:
        return node

    node["sameAs"] = CURRENT_ROOT_URL
    node["description"] = (
        "The Language Archive Cologne (LAC) is a digital archive for long-term "
        "preservation and accessibility of primary language documentation data, "
        "including audio and video recordings, transcriptions, and annotations "
        "of endangered and under-documented languages."
    )
    node["address"] = {
        "@type": "PostalAddress",
        "streetAddress": "Albertus-Magnus-Platz",
        "addressLocality": "Köln",
        "postalCode": "50923",
        "addressCountry": "DE",
    }
    node["geo"] = {
        "@type": "GeoCoordinates",
        "latitude": 50.926464612771746,
        "longitude": 6.929621015158671,
    }
    node["email"] = "lac-helpdesk@uni-koeln.de"
    node["contactPoint"] = {
        "@type": "ContactPoint",
        "contactType": "helpdesk",
        "email": "lac-helpdesk@uni-koeln.de",
    }
    node["hasCertification"] = {
        "@type": "Certification",
        "name": "CoreTrustSeal",
        "url": "https://doi.org/10.34894/961CYL",
        "validFrom": "2024-01-23",
        "validUntil": "2026-04-17",
        "issuedBy": {
            "@type": "Organization",
            "name": "CoreTrustSeal",
            "url": "https://www.coretrustseal.org/",
        },
    }
    node["archiveHeld"] = {
        "@id": f"{root_url}#catalog",
    }
    node["parentOrganization"] = {
        "@type": "Organization",
        "name": "Data Center for the Humanities",
        "url": "https://dch.phil-fak.uni-koeln.de/",
        "parentOrganization": {
            "@type": "Organization",
            "@id": "https://ror.org/00rcxh774",
            "name": "University of Cologne",
        },
    }
    node["memberOf"] = [
        {
            "@type": "Organization",
            "@id": "https://ror.org/03wp25384",
            "name": "CLARIN ERIC",
            "url": "https://www.clarin.eu/",
        },
        {
            "@type": "Organization",
            "name": "Text+",
            "url": "https://text-plus.org/",
        },
        {
            "@type": "Organization",
            "name": "DELAMAN",
            "url": "https://www.delaman.org/",
        },
    ]
    return node


def build_data_catalog_node(root_url: str) -> dict:
    """Minimal ``DataCatalog`` node for ``includedInDataCatalog`` references."""
    return {
        "@type": "DataCatalog",
        "@id": f"{root_url}#catalog",
        "name": ORGANIZATION_NAME,
        "url": root_url,
    }


def build_catalogue_json_ld(public_base_url: str) -> dict:
    current_root_url = f"{public_base_url.rstrip('/')}/"
    catalog_id = f"{PERMANENT_ROOT_URL}#catalog"
    organization_id = f"{PERMANENT_ROOT_URL}#org"

    return {
        "@context": "https://schema.org/",
        "@graph": [
            {
                "@type": "DataCatalog",
                "@id": catalog_id,
                "name": ORGANIZATION_NAME,
                "alternateName": ORGANIZATION_ALTERNATE_NAME,
                "url": current_root_url,
                "description": CATALOGUE_DESCRIPTION,
                "inLanguage": "en",
                "keywords": [
                    "language documentation",
                    "endangered languages",
                    "audiovisual research data",
                    "linguistics",
                ],
                "publisher": {"@id": organization_id},
                "provider": {"@id": organization_id},
            },
            build_organization_node(PERMANENT_ROOT_URL, ORG_DEPTH_FULL),
        ],
    }


def serialize_json_ld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")


def serialize_catalogue_json_ld(public_base_url: str) -> str:
    return serialize_json_ld(build_catalogue_json_ld(public_base_url))
