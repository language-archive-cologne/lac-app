"""Schema.org ``Dataset`` JSON-LD projection for bundle landing pages.

A bundle is projected as a ``Dataset`` that ``isPartOf`` its collection, with
downloadable resources exposed as ``DataDownload`` distributions. Shares field
projections with the collection serializer (issue #152).
"""

from __future__ import annotations

from django.urls import reverse

from lacos.blam.creator_ordering import ordered_bundle_creators
from lacos.explorer import structured_data_fields as fields
from lacos.explorer.structured_data import (
    ORG_DEPTH_MINIMAL,
    ORG_DEPTH_TRIMMED,
    build_data_catalog_node,
    build_organization_node,
    serialize_json_ld,
)


def serialize_bundle_json_ld(bundle, **kwargs) -> str:
    """Serialise the bundle Dataset to a script-safe JSON-LD string."""
    return serialize_json_ld(build_bundle_json_ld(bundle, **kwargs))


def build_bundle_json_ld(  # noqa: PLR0913
    bundle,
    *,
    public_base_url: str,
    access_level: str,
    collection=None,
    publication_info=None,
    creators=None,
    media_resources=None,
    written_resources=None,
    other_resources=None,
    licenses=None,
) -> dict:
    """Build the Schema.org ``Dataset`` JSON-LD for a bundle landing page."""
    root_url = f"{public_base_url.rstrip('/')}/"
    landing_url = _landing_url(
        public_base_url, "explorer:bundle_detail_by_handle", bundle.handle_path
    )

    general_info = bundle.get_general_info
    administrative_info = bundle.get_administrative_info
    if creators is None and publication_info is not None:
        creators = ordered_bundle_creators(publication_info)

    is_handle = bool(bundle.identifier and bundle.identifier.startswith("hdl:"))

    data: dict = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "@id": bundle.handle_url if is_handle else landing_url,
        "name": fields.title(bundle, general_info),
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
                "value": bundle.handle_path,
                "url": bundle.handle_url,
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
        getattr(general_info, "location", None), bundle.identifier
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

    uris = fields.license_uris(licenses, bundle.identifier)
    if uris:
        data["license"] = fields.scalar_or_list(uris)

    creator_nodes = fields.creators(creators or [])
    if creator_nodes:
        data["creator"] = creator_nodes

    is_part_of = _is_part_of(collection, public_base_url)
    if is_part_of:
        data["isPartOf"] = is_part_of

    downloads = fields.data_downloads(
        [
            *(media_resources or []),
            *(written_resources or []),
            *(other_resources or []),
        ]
    )
    if downloads:
        data["distribution"] = downloads

    data["publisher"] = build_organization_node(root_url, ORG_DEPTH_TRIMMED)
    data["includedInDataCatalog"] = build_data_catalog_node(root_url)
    data["sdLicense"] = fields.SD_LICENSE
    data["sdPublisher"] = build_organization_node(root_url, ORG_DEPTH_MINIMAL)

    return data


def _is_part_of(collection, public_base_url: str) -> dict | None:
    if not collection:
        return None
    is_handle = bool(collection.identifier and collection.identifier.startswith("hdl:"))
    landing_url = _landing_url(
        public_base_url,
        "explorer:collection_detail_by_handle",
        collection.handle_path,
    )
    node = {
        "@type": ["Dataset", "Collection"],
        "@id": collection.handle_url if is_handle else landing_url,
        "name": fields.title(collection, collection.get_general_info),
        "url": landing_url,
    }
    return node


def _landing_url(public_base_url: str, route: str, handle: str) -> str:
    return "{}{}".format(
        public_base_url.rstrip("/"),
        reverse(route, kwargs={"handle": handle}),
    )
