"""Schema.org ``Dataset`` JSON-LD projection for collection landing pages.

A deliberately lossy, mechanical projection of the BLAM collection CMDI (issue
#152). Full fidelity stays in the CMDI; this transform never silently repairs
source data -- it reports findings via the module logger instead.
"""

from __future__ import annotations

import logging

from django.urls import reverse

from lacos.blam.creator_ordering import ordered_collection_creators
from lacos.explorer.structured_data import (
    ORG_DEPTH_MINIMAL,
    ORG_DEPTH_TRIMMED,
    build_data_catalog_node,
    build_organization_node,
    serialize_json_ld,
)

logger = logging.getLogger(__name__)

# License of the structured-data record itself (decision 5), not the dataset.
SD_LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"

GLOTTOLOG_LANGUOID_BASE = "https://glottolog.org/resource/languoid/id/"

ACCESS_LEVEL_PUBLIC = "public"

# Controlled strings for non-public access (issue: conditionsOfAccess).
CONDITIONS_OF_ACCESS = {
    "academic": "Available to authenticated members of the academic community.",
    "restricted": "Available on request; contact the repository for access.",
}


def serialize_collection_json_ld(collection, **kwargs) -> str:
    """Serialise the collection Dataset to a script-safe JSON-LD string."""
    return serialize_json_ld(build_collection_json_ld(collection, **kwargs))


def build_collection_json_ld(  # noqa: PLR0913
    collection,
    *,
    public_base_url: str,
    access_level: str,
    publication_info=None,
    creators=None,
    metadata_files=None,
    licenses=None,
) -> dict:
    """Build the Schema.org ``Dataset`` JSON-LD for a collection landing page."""
    root_url = f"{public_base_url.rstrip('/')}/"
    landing_url = "{}{}".format(
        public_base_url.rstrip("/"),
        reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": collection.handle_path},
        ),
    )

    general_info = collection.get_general_info
    administrative_info = collection.get_administrative_info
    if creators is None and publication_info is not None:
        creators = ordered_collection_creators(publication_info)

    is_handle = bool(collection.identifier and collection.identifier.startswith("hdl:"))

    data: dict = {
        "@context": "https://schema.org/",
        "@type": ["Dataset", "Collection"],
        "@id": collection.handle_url if is_handle else landing_url,
        "name": _title(collection, general_info),
    }

    description = _clean(getattr(general_info, "description", "")) if general_info else ""
    if description:
        data["description"] = description

    data["url"] = landing_url

    if is_handle:
        data["identifier"] = [
            {
                "@type": "PropertyValue",
                "propertyID": "hdl",
                "value": collection.handle_path,
                "url": collection.handle_url,
            }
        ]

    version = _clean(getattr(general_info, "version", "")) if general_info else ""
    if version:
        data["version"] = version

    languages = list(general_info.object_languages.all()) if general_info else []
    in_language = _in_language(languages)
    if in_language:
        data["inLanguage"] = _scalar_or_list(in_language)
    about = _about_languages(languages)
    if about:
        data["about"] = _scalar_or_list(about)

    keywords = _keywords(general_info, languages)
    if keywords:
        data["keywords"] = keywords

    spatial = _spatial_coverage(getattr(general_info, "location", None), collection)
    if spatial:
        data["spatialCoverage"] = spatial

    date_published = _date_published(administrative_info, publication_info)
    if date_published:
        data["datePublished"] = date_published

    is_free = access_level == ACCESS_LEVEL_PUBLIC
    data["isAccessibleForFree"] = is_free
    if not is_free:
        condition = CONDITIONS_OF_ACCESS.get(access_level)
        if condition:
            data["conditionsOfAccess"] = condition

    license_uris = _license_uris(licenses, collection)
    if license_uris:
        data["license"] = _scalar_or_list(license_uris)

    copyright_holders = _copyright_holders(administrative_info)
    if copyright_holders:
        data["copyrightHolder"] = _scalar_or_list(copyright_holders)

    creator_nodes = _creators(creators or [])
    if creator_nodes:
        data["creator"] = creator_nodes

    if administrative_info and getattr(administrative_info, "is_derivation_of", ""):
        data["isBasedOn"] = administrative_info.is_derivation_of

    same_as = _same_as(administrative_info)
    if same_as:
        data["sameAs"] = _scalar_or_list(same_as)

    media_objects = _media_objects(metadata_files or [])
    if media_objects:
        data["subjectOf"] = _scalar_or_list(media_objects)

    data["collectionSize"] = collection.bundle_collection.count()

    data["publisher"] = build_organization_node(root_url, ORG_DEPTH_TRIMMED)
    data["includedInDataCatalog"] = build_data_catalog_node(root_url)
    data["sdLicense"] = SD_LICENSE
    data["sdPublisher"] = build_organization_node(root_url, ORG_DEPTH_MINIMAL)

    return data


# ---------------------------------------------------------------------------
# Field projections
# ---------------------------------------------------------------------------


def _title(collection, general_info) -> str:
    if general_info:
        return (
            general_info.display_title
            or getattr(general_info, "title", "")
            or collection.identifier
        )
    return collection.identifier


def _in_language(languages: list) -> list[str]:
    codes = []
    for language in languages:
        code = _clean(language.iso_639_3_code)
        if code and code not in codes:
            codes.append(code)
    return codes


def _about_languages(languages: list) -> list[dict]:
    nodes = []
    for language in languages:
        node = {"@type": "Language"}
        name = _clean(language.name) or _clean(language.display_name)
        if name:
            node["name"] = name
        code = _clean(language.iso_639_3_code)
        if code:
            node["alternateName"] = code
        glottocode = _clean(language.glottolog_code)
        if glottocode:
            node["sameAs"] = f"{GLOTTOLOG_LANGUOID_BASE}{glottocode}"
        if len(node) > 1:
            nodes.append(node)
    return nodes


def _keywords(general_info, languages: list) -> list[str]:
    keywords: list[str] = []
    if general_info:
        for keyword in general_info.keywords.all():
            value = _clean(keyword.value)
            if value and value not in keywords:
                keywords.append(value)
    for language in languages:
        try:
            taxonomy = language.taxonomy
        except Exception:  # noqa: BLE001 - OneToOne may be absent
            taxonomy = None
        if not taxonomy:
            continue
        for family in taxonomy.language_family.all():
            value = _clean(family.value)
            if value and value not in keywords:
                keywords.append(value)
    return keywords


def _spatial_coverage(location, collection) -> dict | None:
    if not location:
        return None
    place: dict = {"@type": "Place"}
    name = _place_name(location)
    if name:
        place["name"] = name
    geo = _geo_coordinates(location, collection)
    if geo:
        place["geo"] = geo
    return place if len(place) > 1 else None


def _place_name(location) -> str:
    parts = [
        _clean(location.location_name) or _clean(location.location_facet),
        _clean(location.region_name) or _clean(location.region_facet),
        _clean(location.country_name) or _clean(location.country_facet),
    ]
    return ", ".join(part for part in parts if part)


def _geo_coordinates(location, collection) -> dict | None:
    raw = _clean(location.geo_location)
    if not raw:
        return None
    if "," not in raw:
        logger.warning(
            "Unparseable CollectionGeoLocation for %s: %r", collection.identifier, raw
        )
        return None
    latitude, longitude = raw.split(",", 1)
    try:
        return {
            "@type": "GeoCoordinates",
            "latitude": float(latitude.strip()),
            "longitude": float(longitude.strip()),
        }
    except ValueError:
        logger.warning(
            "Unparseable CollectionGeoLocation for %s: %r", collection.identifier, raw
        )
        return None


def _date_published(administrative_info, publication_info) -> str | None:
    if administrative_info and getattr(administrative_info, "availability_date", None):
        return _format_date(administrative_info.availability_date)
    if publication_info and getattr(publication_info, "publication_year", None):
        return str(publication_info.publication_year)
    return None


def _license_uris(licenses, collection) -> list[str]:
    uris: list[str] = []
    for license_obj in licenses or []:
        uri = _clean(getattr(license_obj, "license_identifier", ""))
        if not uri or uri in uris:
            continue
        if not _is_recognized_license(uri):
            logger.warning(
                "Non-CC/non-rightsstatements license URI on %s: %r",
                collection.identifier,
                uri,
            )
        uris.append(uri)
    return uris


def _is_recognized_license(uri: str) -> bool:
    lowered = uri.lower()
    return "creativecommons.org" in lowered or "rightsstatements.org" in lowered


def _copyright_holders(administrative_info) -> list[dict]:
    if not administrative_info:
        return []
    nodes = []
    for rights_holder in administrative_info.rights_holders.all():
        node = _agent_node(
            name=_clean(rights_holder.rights_holder_name),
            identifiers=rights_holder.rights_holder_identifiers.all(),
        )
        if node:
            nodes.append(node)
    return nodes


def _agent_node(*, name: str, identifiers) -> dict | None:
    """Project a rights holder to a Person/Organization, typed by identifier.

    The model carries no person/organization flag, so the type is inferred from
    the identifier: ORCID -> Person, ROR -> Organization. With no resolvable
    identifier we default to Organization (rights holders are typically
    institutions) and emit no ``@id``.
    """
    orcid = ror = url = None
    for identifier in identifiers:
        value = _clean(getattr(identifier, "identifier", ""))
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


def _creators(creators: list) -> list[dict]:
    nodes = []
    for creator in creators:
        node = {"@type": "Person"}
        identifier_uri = _person_identifier_uri(creator)
        if identifier_uri:
            node["@id"] = identifier_uri
        given = _clean(getattr(creator, "given_name", ""))
        family = _clean(getattr(creator, "family_name", ""))
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


def _person_identifier_uri(creator) -> str:
    """ORCID/URL identifier URI for a creator; never an email (privacy)."""
    value = _clean(getattr(creator, "name_identifier", ""))
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
    affiliation = _clean(getattr(creator, "affiliation", ""))
    if not affiliation:
        return None
    node = {"@type": "Organization"}
    if affiliation.startswith(("http://", "https://")) and "ror.org" in affiliation.lower():
        node["@id"] = affiliation
    else:
        node["name"] = affiliation
    return node


def _same_as(administrative_info) -> list[str]:
    if not administrative_info:
        return []
    uris = []
    for resource in administrative_info.is_identical_to.all():
        uri = _clean(getattr(resource, "uri", ""))
        if uri and uri not in uris:
            uris.append(uri)
    return uris


def _media_objects(metadata_files: list) -> list[dict]:
    nodes = []
    for metadata_file in metadata_files:
        node = {"@type": "MediaObject"}
        name = _clean(getattr(metadata_file, "file_name", ""))
        if name:
            node["name"] = name
        content_url = _persistent_uri(getattr(metadata_file, "file_pid", ""))
        if content_url:
            node["contentUrl"] = content_url
        encoding = _clean(getattr(metadata_file, "mime_type", ""))
        if encoding:
            node["encodingFormat"] = encoding
        description = _clean(getattr(metadata_file, "file_description", ""))
        if description:
            node["description"] = description
        if len(node) > 1:
            nodes.append(node)
    return nodes


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _clean(value) -> str:
    return (value or "").strip() if isinstance(value, str) else (value or "")


def _format_date(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _persistent_uri(value: str) -> str:
    value = _clean(value)
    if not value:
        return ""
    if value.startswith("hdl:"):
        return f"https://hdl.handle.net/{value[4:]}"
    if value.startswith(("http://", "https://")):
        return value
    return ""


def _scalar_or_list(items: list):
    return items[0] if len(items) == 1 else items
