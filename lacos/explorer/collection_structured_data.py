"""Schema.org ``Dataset`` JSON-LD projection for collection landing pages.

A deliberately lossy, mechanical projection of the BLAM collection CMDI (issue
#152). Full fidelity stays in the CMDI; this transform never silently repairs
source data -- it reports findings via the module logger instead.
"""

from __future__ import annotations

from django.urls import reverse

from lacos.blam.creator_ordering import ordered_collection_creators
from lacos.explorer import structured_data_fields as fields
from lacos.explorer.structured_data import (
    ORG_DEPTH_MINIMAL,
    ORG_DEPTH_TRIMMED,
    build_data_catalog_node,
    build_organization_node,
    serialize_json_ld,
)


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
        "name": fields.title(collection, general_info),
    }

    description = fields.clean(getattr(general_info, "description", "")) if general_info else ""
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

    version = fields.clean(getattr(general_info, "version", "")) if general_info else ""
    if version:
        data["version"] = version

    languages = list(general_info.object_languages.all()) if general_info else []
    codes = fields.in_language(languages)
    if codes:
        data["inLanguage"] = fields.scalar_or_list(codes)
    about = fields.about_languages(languages)
    if about:
        data["about"] = fields.scalar_or_list(about)

    keywords = fields.keywords(general_info, languages)
    if keywords:
        data["keywords"] = keywords

    spatial = fields.spatial_coverage(
        getattr(general_info, "location", None), collection.identifier
    )
    if spatial:
        data["spatialCoverage"] = spatial

    published = fields.date_published(administrative_info, publication_info)
    if published:
        data["datePublished"] = published

    is_free = access_level == fields.ACCESS_LEVEL_PUBLIC
    data["isAccessibleForFree"] = is_free
    if not is_free:
        condition = fields.CONDITIONS_OF_ACCESS.get(access_level)
        if condition:
            data["conditionsOfAccess"] = condition

    uris = fields.license_uris(licenses, collection.identifier)
    if uris:
        data["license"] = fields.scalar_or_list(uris)

    copyright_holders = _copyright_holders(administrative_info)
    if copyright_holders:
        data["copyrightHolder"] = fields.scalar_or_list(copyright_holders)

    creator_nodes = fields.creators(creators or [])
    if creator_nodes:
        data["creator"] = creator_nodes

    if administrative_info and getattr(administrative_info, "is_derivation_of", ""):
        data["isBasedOn"] = administrative_info.is_derivation_of

    same_as = _same_as(administrative_info)
    if same_as:
        data["sameAs"] = fields.scalar_or_list(same_as)

    subject_of = fields.media_objects(metadata_files or [])
    if subject_of:
        data["subjectOf"] = fields.scalar_or_list(subject_of)

    data["collectionSize"] = collection.bundle_collection.count()

    data["publisher"] = build_organization_node(root_url, ORG_DEPTH_TRIMMED)
    data["includedInDataCatalog"] = build_data_catalog_node(root_url)
    data["sdLicense"] = fields.SD_LICENSE
    data["sdPublisher"] = build_organization_node(root_url, ORG_DEPTH_MINIMAL)

    return data


def _copyright_holders(administrative_info) -> list[dict]:
    if not administrative_info:
        return []
    nodes = []
    for rights_holder in administrative_info.rights_holders.all():
        node = fields.agent_node(
            name=fields.clean(rights_holder.rights_holder_name),
            identifiers=rights_holder.rights_holder_identifiers.all(),
        )
        if node:
            nodes.append(node)
    return nodes


def _same_as(administrative_info) -> list[str]:
    if not administrative_info:
        return []
    uris = []
    for resource in administrative_info.is_identical_to.all():
        uri = fields.clean(getattr(resource, "uri", ""))
        if uri and uri not in uris:
            uris.append(uri)
    return uris
