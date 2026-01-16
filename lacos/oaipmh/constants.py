"""Repository configuration and shared OAI-PMH constants."""

from __future__ import annotations

REPO_NAME = "LACOS Repository"
REPO_ADMIN_EMAIL = "support@example.com"
REPO_PROTOCOL_VERSION = "2.0"
REPO_DELETED_RECORD = "no"
REPO_GRANULARITY = "YYYY-MM-DDThh:mm:ssZ"
REPO_EARLIEST_DATASTAMP = "1970-01-01T00:00:00Z"
REPO_IDENTIFIER = "lacos"
REPO_BASE_ENDPOINT = "/oai/"

# Metadata formats supported by the LACOS OAI-PMH endpoint.
# Actual field mappings are supplied by lacos.oaipmh.mappings.
SUPPORTED_METADATA_FORMATS = (
    {
        "metadata_prefix": "blam",
        "schema": "https://infra.clarin.eu/CMDI/1.x/xsd/cmd-component.xsd",
        "namespace": "http://www.clarin.eu/cmd/",
    },
    {
        "metadata_prefix": "oai_dc",
        "schema": "http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
        "namespace": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    },
    {
        "metadata_prefix": "olac",
        "schema": "http://www.language-archives.org/OLAC/1.1/olac.xsd",
        "namespace": "http://www.language-archives.org/OLAC/1.1/",
    },
    {
        "metadata_prefix": "schema_org",
        "schema": "https://schema.org/docs/schemaorg.owl",
        "namespace": "https://schema.org/",
    },
)

SUPPORTED_SETS = {
    "collections": "Collections",
    "bundles": "Bundles",
}

DEFAULT_PAGE_SIZE = 10
