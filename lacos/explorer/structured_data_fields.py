"""Shared Schema.org field projections for collection and bundle landing pages.

Pure, model-agnostic helpers used by both ``collection_structured_data`` and
``bundle_structured_data``. They never repair source data -- defects are
reported via the module logger (issue #152, design decision 4).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("lacos.explorer.structured_data")

GLOTTOLOG_LANGUOID_BASE = "https://glottolog.org/resource/languoid/id/"

ACCESS_LEVEL_PUBLIC = "public"

# License of the structured-data record itself (not the dataset).
SD_LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"

# Controlled strings for non-public access (conditionsOfAccess).
CONDITIONS_OF_ACCESS = {
    "academic": "Available to authenticated members of the academic community.",
    "restricted": "Available on request; contact the repository for access.",
}


# ---------------------------------------------------------------------------
# Scalars / small helpers
# ---------------------------------------------------------------------------


def clean(value) -> str:
    return (value or "").strip() if isinstance(value, str) else (value or "")


def format_date(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def persistent_uri(value: str) -> str:
    value = clean(value)
    if not value:
        return ""
    if value.startswith("hdl:"):
        return f"https://hdl.handle.net/{value[4:]}"
    if value.startswith(("http://", "https://")):
        return value
    return ""


def scalar_or_list(items: list):
    return items[0] if len(items) == 1 else items


def title(obj, general_info) -> str:
    if general_info:
        return (
            general_info.display_title
            or getattr(general_info, "title", "")
            or obj.identifier
        )
    return obj.identifier


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------


def in_language(languages: list) -> list[str]:
    codes = []
    for language in languages:
        code = clean(language.iso_639_3_code)
        if code and code not in codes:
            codes.append(code)
    return codes


def about_languages(languages: list) -> list[dict]:
    nodes = []
    for language in languages:
        node = {"@type": "Language"}
        name = clean(language.name) or clean(language.display_name)
        if name:
            node["name"] = name
        code = clean(language.iso_639_3_code)
        if code:
            node["alternateName"] = code
        glottocode = clean(language.glottolog_code)
        if glottocode:
            node["sameAs"] = f"{GLOTTOLOG_LANGUOID_BASE}{glottocode}"
        if len(node) > 1:
            nodes.append(node)
    return nodes


def keywords(general_info, languages: list) -> list[str]:
    values: list[str] = []
    if general_info:
        for keyword in general_info.keywords.all():
            value = clean(keyword.value)
            if value and value not in values:
                values.append(value)
    for language in languages:
        taxonomy = _language_taxonomy(language)
        if not taxonomy:
            continue
        for family in taxonomy.language_family.all():
            value = clean(family.value)
            if value and value not in values:
                values.append(value)
    return values


def _language_taxonomy(language):
    """Reverse OneToOne taxonomy; collections and bundles use different names."""
    for attr in ("taxonomy", "bundle_object_language_taxonomy"):
        try:
            taxonomy = getattr(language, attr)
        except Exception:  # noqa: BLE001 - OneToOne may be absent / wrong name
            continue
        if taxonomy:
            return taxonomy
    return None


# ---------------------------------------------------------------------------
# Spatial coverage
# ---------------------------------------------------------------------------


def spatial_coverage(location, identifier: str) -> dict | None:
    if not location:
        return None
    place: dict = {"@type": "Place"}
    name = _place_name(location)
    if name:
        place["name"] = name
    geo = _geo_coordinates(location, identifier)
    if geo:
        place["geo"] = geo
    return place if len(place) > 1 else None


def _place_name(location) -> str:
    parts = [
        clean(location.location_name) or clean(location.location_facet),
        clean(location.region_name) or clean(location.region_facet),
        clean(location.country_name) or clean(location.country_facet),
    ]
    return ", ".join(part for part in parts if part)


def _geo_coordinates(location, identifier: str) -> dict | None:
    raw = clean(location.geo_location)
    if not raw:
        return None
    if "," not in raw:
        logger.warning("Unparseable geo location for %s: %r", identifier, raw)
        return None
    latitude, longitude = raw.split(",", 1)
    try:
        return {
            "@type": "GeoCoordinates",
            "latitude": float(latitude.strip()),
            "longitude": float(longitude.strip()),
        }
    except ValueError:
        logger.warning("Unparseable geo location for %s: %r", identifier, raw)
        return None


# ---------------------------------------------------------------------------
# Access rights / dates / licenses
# ---------------------------------------------------------------------------


def date_published(administrative_info, publication_info) -> str | None:
    if administrative_info and getattr(administrative_info, "availability_date", None):
        return format_date(administrative_info.availability_date)
    if publication_info and getattr(publication_info, "publication_year", None):
        return str(publication_info.publication_year)
    return None


def license_uris(licenses, identifier: str) -> list[str]:
    uris: list[str] = []
    for license_obj in licenses or []:
        uri = clean(getattr(license_obj, "license_identifier", ""))
        if not uri or uri in uris:
            continue
        if not _is_recognized_license(uri):
            logger.warning(
                "Non-CC/non-rightsstatements license URI on %s: %r", identifier, uri
            )
        uris.append(uri)
    return uris


def _is_recognized_license(uri: str) -> bool:
    lowered = uri.lower()
    return "creativecommons.org" in lowered or "rightsstatements.org" in lowered


# ---------------------------------------------------------------------------
# Agents (creators, rights holders)
# ---------------------------------------------------------------------------


def creators(creator_list: list) -> list[dict]:
    nodes = []
    for creator in creator_list:
        node = {"@type": "Person"}
        identifier_uri = person_identifier_uri(creator)
        if identifier_uri:
            node["@id"] = identifier_uri
        given = clean(getattr(creator, "given_name", ""))
        family = clean(getattr(creator, "family_name", ""))
        if given:
            node["givenName"] = given
        if family:
            node["familyName"] = family
        name = " ".join(part for part in (given, family) if part)
        if name:
            node["name"] = name
        affiliation = _affiliation_node(creator)
        if affiliation:
            node["affiliation"] = affiliation
        if name or "@id" in node:
            nodes.append(node)
    return nodes


def person_identifier_uri(creator) -> str:
    """ORCID/URL identifier URI for a creator; never an email (privacy)."""
    value = clean(getattr(creator, "name_identifier", ""))
    if not value:
        return ""
    identifier_type = (getattr(creator, "name_identifier_type", "") or "").upper()
    if identifier_type == "EMAIL":
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if identifier_type == "ORCID":
        return f"https://orcid.org/{value}"
    return ""


def _affiliation_node(creator) -> dict | None:
    affiliation = clean(getattr(creator, "affiliation", ""))
    if not affiliation:
        return None
    node = {"@type": "Organization"}
    if affiliation.startswith(("http://", "https://")) and "ror.org" in affiliation.lower():
        node["@id"] = affiliation
    else:
        node["name"] = affiliation
    return node


def agent_node(*, name: str, identifiers) -> dict | None:
    """Project a rights holder to a Person/Organization, typed by identifier.

    The model carries no person/organization flag, so the type is inferred from
    the identifier: ORCID -> Person, ROR -> Organization. With no resolvable
    identifier we default to Organization (rights holders are typically
    institutions) and emit no ``@id``.
    """
    orcid = ror = url = None
    for identifier in identifiers:
        value = clean(getattr(identifier, "identifier", ""))
        if not value:
            continue
        identifier_type = (getattr(identifier, "identifier_type", "") or "").upper()
        if identifier_type == "ORCID":
            orcid = value if value.startswith("http") else f"https://orcid.org/{value}"
        elif "ror.org" in value.lower():
            ror = value if value.startswith("http") else f"https://{value}"
        elif value.startswith(("http://", "https://")):
            url = value

    if orcid:
        node = {"@type": "Person", "@id": orcid}
    elif ror:
        node = {"@type": "Organization", "@id": ror}
    elif url:
        node = {"@type": "Organization", "@id": url}
    else:
        node = {"@type": "Organization"}

    if name:
        node["name"] = name
    return node if name or "@id" in node else None


# ---------------------------------------------------------------------------
# Files: metadata records (subjectOf) and downloads (distribution)
# ---------------------------------------------------------------------------


def media_objects(metadata_files: list) -> list[dict]:
    nodes = []
    for metadata_file in metadata_files:
        node = {"@type": "MediaObject"}
        name = clean(getattr(metadata_file, "file_name", ""))
        if name:
            node["name"] = name
        content_url = persistent_uri(getattr(metadata_file, "file_pid", ""))
        if content_url:
            node["contentUrl"] = content_url
        encoding = clean(getattr(metadata_file, "mime_type", ""))
        if encoding:
            node["encodingFormat"] = encoding
        description = clean(getattr(metadata_file, "file_description", ""))
        if description:
            node["description"] = description
        if len(node) > 1:
            nodes.append(node)
    return nodes


def data_downloads(resources: list) -> list[dict]:
    nodes = []
    for resource in resources:
        node = {"@type": "DataDownload"}
        name = clean(getattr(resource, "file_name", ""))
        if name:
            node["name"] = name
        content_url = persistent_uri(getattr(resource, "file_pid", ""))
        if content_url:
            node["contentUrl"] = content_url
        encoding = clean(getattr(resource, "mime_type", ""))
        if encoding:
            node["encodingFormat"] = encoding
        if len(node) > 1:
            nodes.append(node)
    return nodes
