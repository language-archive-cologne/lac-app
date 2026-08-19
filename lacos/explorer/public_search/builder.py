"""Build the anonymous public search index from repository metadata."""

from __future__ import annotations

from typing import Any

from django.db.models import Count

from lacos.explorer.facet_querysets import bundle_facet_queryset
from lacos.explorer.facet_querysets import collection_facet_queryset
from lacos.explorer.public_search.schema import finalize_public_search_index
from lacos.storage.services.exposure_policy_service import ExposurePolicyService


def build_public_search_index(
    *,
    policy: ExposurePolicyService | None = None,
) -> dict[str, Any]:
    exposure = policy or ExposurePolicyService()
    anonymous = exposure.anonymous_user()
    collection_queryset = exposure.filter_collection_queryset(
        anonymous,
        collection_facet_queryset(),
        channel="search",
    )
    bundle_queryset = exposure.filter_bundle_queryset(
        anonymous,
        bundle_facet_queryset(),
        channel="search",
    )
    collections = [
        _collection_record(collection)
        for collection in _prepare_collections(collection_queryset)
    ]
    bundles = [_bundle_record(bundle) for bundle in _prepare_bundles(bundle_queryset)]
    return finalize_public_search_index(
        {
            "collections": collections,
            "bundles": bundles,
        },
    )


def _prepare_collections(queryset):
    return (
        queryset.annotate(bundles_count=Count("bundle_collection", distinct=True))
        .order_by("identifier")
        .prefetch_related(
            "general_info__keywords",
            "general_info__object_languages__alternative_names",
            "publication_info__creators",
            "publication_info__contributors",
            "administrative_info__licenses",
            "project_infos__funder_infos",
            "bundle_file_type_facets",
        )
    )


def _prepare_bundles(queryset):
    return queryset.order_by("identifier").prefetch_related(
        "general_info__keywords",
        "general_info__object_languages__alternative_names",
        "publication_info__creators",
        "publication_info__contributors__contributor_name",
        "administrative_info__licenses",
        "projects__funder_infos",
        "file_type_facets",
        "structural_info__is_member_of_collection__general_info",
    )


def _collection_record(collection) -> dict[str, Any]:
    general = collection.get_general_info
    publication = collection.get_publication_info
    location = getattr(general, "location", None)
    keywords = _keyword_values(general)
    languages = _language_values(general)
    licenses = _license_values(collection.get_administrative_info)
    file_types = sorted(
        {
            item.file_type
            for item in collection.bundle_file_type_facets.all()
            if item.file_type
        },
    )
    access = getattr(collection, "acl_access_level", "") or ""
    year = getattr(publication, "publication_year", None)
    record = {
        "identifier": collection.identifier,
        "handle_path": collection.handle_path,
        "title": getattr(general, "display_title", "") or collection.identifier,
        "description": getattr(general, "description", "") or "",
        "keywords": keywords,
        "languages": languages,
        "location": _location_value(location),
        "publication": _publication_value(publication),
        "grant_ids": _grant_values(collection.project_infos.all()),
        "acl_access_level": access,
        "licenses": licenses,
        "file_types": file_types,
        "bundles_count": collection.bundles_count,
        "facets": {
            "keyword": keywords,
            "language": [language["code"] for language in languages],
            "file_type": file_types,
            "year": [str(year)] if year is not None else [],
            "country": _present(getattr(location, "country_facet", "")),
            "region": _present(getattr(location, "region_facet", "")),
            "access": _present(access),
            "license": licenses,
        },
    }
    record["search"] = _search_fields(record, general=general)
    return record


def _bundle_record(bundle) -> dict[str, Any]:
    general = bundle.get_general_info
    publication = bundle.get_publication_info
    structural = bundle.get_structural_info
    parent = getattr(structural, "is_member_of_collection", None)
    parent_general = parent.get_general_info if parent else None
    location = getattr(general, "location", None)
    keywords = _keyword_values(general)
    languages = _language_values(general)
    licenses = _license_values(bundle.get_administrative_info)
    file_types = sorted(
        {item.file_type for item in bundle.file_type_facets.all() if item.file_type},
    )
    access = getattr(bundle, "acl_access_level", "") or ""
    year = getattr(publication, "publication_year", None)
    collection = None
    if parent is not None:
        collection = {
            "identifier": parent.identifier,
            "handle_path": parent.handle_path,
            "title": getattr(parent_general, "display_title", "") or parent.identifier,
        }
    record = {
        "identifier": bundle.identifier,
        "handle_path": bundle.handle_path,
        "title": getattr(general, "display_title", "") or bundle.identifier,
        "description": getattr(general, "description", "") or "",
        "keywords": keywords,
        "languages": languages,
        "location": _location_value(location),
        "publication": _publication_value(publication),
        "grant_ids": _grant_values(bundle.projects.all()),
        "acl_access_level": access,
        "licenses": licenses,
        "file_types": file_types,
        "collection": collection,
        "facets": {
            "keyword": keywords,
            "language": [language["code"] for language in languages],
            "file_type": file_types,
            "collection": [parent.identifier] if parent else [],
            "year": [str(year)] if year is not None else [],
            "country": _present(getattr(location, "country_facet", "")),
            "region": _present(getattr(location, "region_facet", "")),
            "access": _present(access),
            "license": licenses,
        },
    }
    record["search"] = _search_fields(record, general=general)
    return record


def _keyword_values(general) -> list[str]:
    if general is None:
        return []
    return sorted(
        {keyword.value for keyword in general.keywords.all() if keyword.value},
    )


def _language_values(general) -> list[dict[str, str]]:
    if general is None:
        return []
    return sorted(
        (
            {
                "code": language.iso_639_3_code,
                "name": language.name,
                "display_name": language.display_name,
                "alternative_names": sorted(
                    value.value
                    for value in language.alternative_names.all()
                    if value.value
                ),
            }
            for language in general.object_languages.all()
        ),
        key=lambda item: (item["name"].casefold(), item["code"]),
    )


def _location_value(location) -> dict[str, str]:
    return {
        "name": getattr(location, "location_name", "") or "",
        "country": getattr(location, "country_facet", "") or "",
        "country_name": getattr(location, "country_name", "") or "",
        "region": getattr(location, "region_facet", "") or "",
        "geo": getattr(location, "geo_location", "") or "",
    }


def _publication_value(publication) -> dict[str, Any]:
    if publication is None:
        return {
            "year": None,
            "provider": "",
            "creators": [],
            "contributors": [],
        }
    return {
        "year": publication.publication_year,
        "provider": publication.data_provider,
        "creators": [_person_value(person) for person in publication.creators.all()],
        "contributors": [
            _person_value(person, contributor=True)
            for person in publication.contributors.all()
        ],
    }


def _person_value(person, *, contributor: bool = False) -> dict[str, str]:
    related_name = getattr(person, "contributor_name", None) if contributor else None
    family_name = getattr(person, "family_name", "") or getattr(
        related_name,
        "contributor_family_name",
        "",
    )
    given_name = getattr(person, "given_name", "") or getattr(
        related_name,
        "contributor_given_name",
        "",
    )
    return {
        "family_name": family_name or "",
        "given_name": given_name or "",
        "display_name": getattr(person, "contributor_display_name", "") or "",
        "role": getattr(person, "role", "") or "",
    }


def _license_values(administrative) -> list[str]:
    if administrative is None:
        return []
    return sorted(
        {
            license_value.license_name
            for license_value in administrative.licenses.all()
            if license_value.license_name
        },
    )


def _grant_values(projects) -> list[str]:
    return sorted(
        {
            funder.grant_identifier
            for project in projects
            for funder in project.funder_infos.all()
            if funder.grant_identifier
        },
    )


def _search_fields(record: dict[str, Any], *, general) -> dict[str, list[str]]:
    publication = record["publication"]
    location = record["location"]
    languages = record["languages"]
    collection = record.get("collection") or {}
    return {
        "identifier": _present(record["identifier"]),
        "title": _present(record["title"]),
        "description": _present(record["description"]),
        "keyword": record["keywords"],
        "language": [
            value
            for language in languages
            for value in (
                language["name"],
                language["display_name"],
                language["code"],
                *language["alternative_names"],
            )
            if value
        ],
        "location": [value for value in location.values() if value],
        "creator": [
            value
            for person in publication["creators"]
            for value in person.values()
            if value
        ],
        "contributor": [
            value
            for person in publication["contributors"]
            for value in person.values()
            if value
        ],
        "grant_id": record["grant_ids"],
        "collection": [value for value in collection.values() if value],
        "provider": _present(publication["provider"]),
    }


def _present(value) -> list[str]:
    return [str(value)] if value not in (None, "") else []
