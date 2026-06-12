"""Structured data payloads for public explorer pages."""

import json

CATALOGUE_DESCRIPTION = (
    "The Language Archive Cologne is a digital archive of language resources "
    "containing collections of primary language data, including audio and video "
    "recordings, as well as linguistic analyses."
)


def build_catalogue_json_ld(public_base_url: str) -> dict:
    root_url = f"{public_base_url.rstrip('/')}/"
    catalog_id = f"{root_url}#catalog"
    organization_id = f"{root_url}#org"

    return {
        "@context": "https://schema.org/",
        "@graph": [
            {
                "@type": "DataCatalog",
                "@id": catalog_id,
                "name": "Language Archive Cologne",
                "alternateName": "LAC",
                "url": root_url,
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
            {
                "@type": "Organization",
                "@id": organization_id,
                "name": "Language Archive Cologne",
                "alternateName": "LAC",
                "url": root_url,
                "identifier": {
                    "@type": "PropertyValue",
                    "propertyID": "re3data",
                    "value": "r3d100012786",
                    "url": "https://doi.org/10.17616/R3JV4W",
                },
                "contactPoint": {
                    "@type": "ContactPoint",
                    "contactType": "helpdesk",
                    "email": "lac-helpdesk@uni-koeln.de",
                },
                "parentOrganization": {
                    "@type": "Organization",
                    "name": "Data Center for the Humanities",
                    "url": "https://dch.phil-fak.uni-koeln.de/",
                    "parentOrganization": {
                        "@type": "Organization",
                        "@id": "https://ror.org/00rcxh774",
                        "name": "University of Cologne",
                    },
                },
                "memberOf": [
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
                ],
            },
        ],
    }


def serialize_json_ld(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2).replace("<", "\\u003c")


def serialize_catalogue_json_ld(public_base_url: str) -> str:
    return serialize_json_ld(build_catalogue_json_ld(public_base_url))
