"""HTML head metadata for public collection and bundle landing pages."""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from lacos.blam.models.base_indentifiers import PersonIdentifierTypeChoices

LAC_PUBLISHER_NAME = "Language Archive Cologne"
LAC_RE3DATA_URL = "https://doi.org/10.17616/R3JV4W"


@dataclass(frozen=True)
class MetaTag:
    name: str
    content: str


@dataclass(frozen=True)
class LinkTag:
    rel: str
    href: str
    type: str = ""


def build_collection_head_metadata(  # noqa: PLR0913
    collection,
    *,
    public_base_url: str,
    access_level: str,
    publication_info=None,
    creators=None,
    metadata_files=None,
    licenses=None,
) -> dict[str, list]:
    metadata_routes = [
        ("application/ld+json", "explorer:collection_jsonld_by_handle"),
        ("application/xml", "explorer:collection_xml_by_handle"),
    ]
    return _build_landing_page_metadata(
        obj=collection,
        access_level=access_level,
        publication_info=publication_info,
        creators=creators or [],
        metadata_files=metadata_files or [],
        licenses=licenses or [],
        describedby_routes=[
            (
                media_type,
                _absolute_url(
                    public_base_url,
                    reverse(route, kwargs={"handle": collection.handle_path}),
                ),
            )
            for media_type, route in metadata_routes
        ],
    )


def build_bundle_head_metadata(  # noqa: PLR0913
    bundle,
    *,
    public_base_url: str,
    access_level: str,
    collection=None,
    publication_info=None,
    creators=None,
    metadata_files=None,
    media_resources=None,
    written_resources=None,
    other_resources=None,
    licenses=None,
) -> dict[str, list]:
    metadata_routes = [
        ("application/ld+json", "explorer:bundle_jsonld_by_handle"),
        ("application/xml", "explorer:bundle_xml_by_handle"),
    ]
    metadata = _build_landing_page_metadata(
        obj=bundle,
        access_level=access_level,
        publication_info=publication_info,
        creators=creators or [],
        metadata_files=metadata_files or [],
        licenses=licenses or [],
        describedby_routes=[
            (
                media_type,
                _absolute_url(
                    public_base_url,
                    reverse(route, kwargs={"handle": bundle.handle_path}),
                ),
            )
            for media_type, route in metadata_routes
        ],
    )
    collection_url = _persistent_uri(getattr(collection, "identifier", ""))
    if collection_url:
        metadata["links"].append(LinkTag("collection", collection_url))
        metadata["links"].append(LinkTag("DCTERMS.isPartOf", collection_url))

    for resource in [
        *(media_resources or []),
        *(written_resources or []),
        *(other_resources or []),
    ]:
        resource_url = _persistent_uri(getattr(resource, "file_pid", ""))
        if resource_url:
            metadata["links"].append(
                LinkTag("item", resource_url, getattr(resource, "mime_type", "")),
            )

    return metadata


def _build_landing_page_metadata(  # noqa: PLR0913
    *,
    obj,
    access_level: str,
    publication_info,
    creators: list,
    metadata_files: list,
    licenses: list,
    describedby_routes: list[tuple[str, str]],
) -> dict[str, list]:
    general_info = obj.get_general_info
    location = getattr(general_info, "location", None) if general_info else None
    languages = list(general_info.object_languages.all()) if general_info else []
    keywords = list(general_info.keywords.all()) if general_info else []

    meta = [
        *_base_meta(obj, general_info, access_level, publication_info),
        *[MetaTag("DC.creator", _person_name(creator)) for creator in creators],
        *_language_meta(languages),
        *[MetaTag("DC.subject", keyword.value) for keyword in keywords],
        *[
            MetaTag("DCTERMS.rightsHolder", rights_holder.rights_holder_name)
            for rights_holder in _rights_holders(obj)
        ],
        *[MetaTag("DCTERMS.spatial", value) for value in _spatial_values(location)],
        *_metadata_file_format_meta(metadata_files),
    ]

    links = [
        *_base_links(obj),
        *_creator_links(creators),
        *_language_links(languages),
        *_license_links(licenses),
        *[
            LinkTag("describedby", href, media_type)
            for media_type, href in describedby_routes
        ],
        *_metadata_file_links(metadata_files),
    ]

    return {"meta": _dedupe_meta(meta), "links": _dedupe_links(links)}


def _base_meta(obj, general_info, access_level: str, publication_info) -> list[MetaTag]:
    description = getattr(general_info, "description", "") if general_info else ""
    meta = [
        MetaTag("DC.title", _title(obj, general_info)),
        MetaTag("DC.publisher", LAC_PUBLISHER_NAME),
        MetaTag("DC.type", "Dataset"),
        MetaTag("DC.identifier", obj.identifier),
        MetaTag("DCTERMS.accessRights", access_level),
    ]
    if description:
        meta.append(MetaTag("DC.description", description))
    if publication_info and getattr(publication_info, "publication_year", None):
        meta.append(MetaTag("DCTERMS.issued", str(publication_info.publication_year)))
    if general_info and getattr(general_info, "recording_date", None):
        meta.append(MetaTag("DCTERMS.created", general_info.recording_date.isoformat()))
    return meta


def _language_meta(languages: list) -> list[MetaTag]:
    meta = []
    for language in languages:
        meta.append(MetaTag("DC.language", language.iso_639_3_code))
        meta.append(MetaTag("DC.subject", language.display_name or language.name))
    return meta


def _base_links(obj) -> list[LinkTag]:
    links = [
        LinkTag("schema.DC", "http://purl.org/dc/elements/1.1/"),
        LinkTag("schema.DCTERMS", "http://purl.org/dc/terms/"),
        LinkTag("DC.publisher", LAC_RE3DATA_URL),
        LinkTag("type", "https://schema.org/Dataset"),
        LinkTag("type", "https://schema.org/AboutPage"),
    ]
    persistent_url = _persistent_uri(obj.identifier)
    if persistent_url:
        links.extend(
            [
                LinkTag("cite-as", persistent_url),
                LinkTag("DC.identifier", persistent_url),
            ],
        )
    return links


def _creator_links(creators: list) -> list[LinkTag]:
    links = []
    for creator in creators:
        creator_uri = _person_identifier_uri(creator)
        if creator_uri:
            links.append(LinkTag("author", creator_uri))
            links.append(LinkTag("DC.creator", creator_uri))
    return links


def _language_links(languages: list) -> list[LinkTag]:
    return [
        LinkTag(
            "DC.subject",
            f"https://glottolog.org/resource/languoid/id/{language.glottolog_code}",
        )
        for language in languages
        if language.glottolog_code
    ]


def _license_links(licenses: list) -> list[LinkTag]:
    links = []
    for license_obj in licenses:
        license_url = getattr(license_obj, "license_identifier", "")
        if license_url:
            links.append(LinkTag("license", license_url))
            links.append(LinkTag("DCTERMS.license", license_url))
    return links


def _metadata_file_links(metadata_files: list) -> list[LinkTag]:
    links = []
    for metadata_file in metadata_files:
        metadata_url = _persistent_uri(getattr(metadata_file, "file_pid", ""))
        if metadata_url:
            links.append(
                LinkTag(
                    "describedby",
                    metadata_url,
                    getattr(metadata_file, "mime_type", ""),
                ),
            )
    return links


def _metadata_file_format_meta(metadata_files: list) -> list[MetaTag]:
    return [
        MetaTag("DC.format", resource.mime_type)
        for resource in metadata_files
        if getattr(resource, "mime_type", "")
    ]


def _absolute_url(public_base_url: str, path: str) -> str:
    return f"{public_base_url.rstrip('/')}{path}"


def _title(obj, general_info) -> str:
    if general_info:
        return (
            general_info.display_title
            or getattr(general_info, "title", "")
            or obj.identifier
        )
    return obj.identifier


def _person_name(person) -> str:
    parts = [getattr(person, "family_name", ""), getattr(person, "given_name", "")]
    return ", ".join(part for part in parts if part)


def _person_identifier_uri(person) -> str:
    identifier = (getattr(person, "name_identifier", "") or "").strip()
    if not identifier:
        return ""
    if identifier.startswith(("http://", "https://")):
        return identifier
    identifier_type = (getattr(person, "name_identifier_type", "") or "").upper()
    if identifier_type == PersonIdentifierTypeChoices.ORCID:
        return f"https://orcid.org/{identifier}"
    return ""


def _persistent_uri(value: str) -> str:
    if not value:
        return ""
    if value.startswith("hdl:"):
        return f"https://hdl.handle.net/{value[4:]}"
    if value.startswith(("http://", "https://")):
        return value
    return ""


def _rights_holders(obj) -> list:
    administrative_info = obj.get_administrative_info
    if not administrative_info:
        return []
    return list(administrative_info.rights_holders.all())


def _spatial_values(location) -> list[str]:
    if not location:
        return []
    values = []
    if location.geo_location:
        values.append(location.geo_location)
    if location.location_name:
        values.append(location.location_name)
    if location.region_name:
        values.append(location.region_name)
    if location.country_name:
        values.append(location.country_name)
    if location.country_code:
        values.append(location.country_code)
    return values


def _dedupe_meta(meta: list[MetaTag]) -> list[MetaTag]:
    seen = set()
    result = []
    for item in meta:
        key = (item.name, item.content)
        if item.content and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _dedupe_links(links: list[LinkTag]) -> list[LinkTag]:
    seen = set()
    result = []
    for item in links:
        key = (item.rel, item.href, item.type)
        if item.href and key not in seen:
            seen.add(key)
            result.append(item)
    return result
