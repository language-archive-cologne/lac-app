"""Template-compatible records reconstructed from public index entries."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any


class RelatedValues(tuple):
    """Small immutable replacement for prefetched related managers in templates."""

    __slots__ = ()

    def all(self):
        return self


@dataclass(frozen=True)
class PublicKeyword:
    value: str


@dataclass(frozen=True)
class PublicLanguage:
    iso_639_3_code: str
    name: str
    display_name: str


@dataclass(frozen=True)
class PublicLocation:
    location_name: str
    country_name: str
    country_facet: str
    region_facet: str
    geo_location: str


@dataclass(frozen=True)
class PublicPerson:
    family_name: str = ""
    given_name: str = ""
    contributor_display_name: str = ""
    role: str = ""
    contributor_name: Any = None


@dataclass(frozen=True)
class PublicContributorName:
    contributor_family_name: str = ""
    contributor_given_name: str = ""


@dataclass(frozen=True)
class PublicGeneralInfo:
    display_title: str
    description: str
    keywords: RelatedValues
    object_languages: RelatedValues
    location: PublicLocation


@dataclass(frozen=True)
class PublicPublicationInfo:
    publication_year: int | None
    data_provider: str
    creators: RelatedValues
    contributors: RelatedValues


@dataclass(frozen=True)
class PublicCollectionReference:
    identifier: str
    handle_path: str
    get_general_info: PublicGeneralInfo


@dataclass(frozen=True)
class PublicStructuralInfo:
    is_member_of_collection: PublicCollectionReference | None


@dataclass
class PublicSearchRecord:
    identifier: str
    handle_path: str
    get_general_info: PublicGeneralInfo
    get_publication_info: PublicPublicationInfo
    acl_access_level: str
    bundles_count: int = 0
    get_structural_info: PublicStructuralInfo | None = None
    search_match_reasons: tuple[str, ...] = field(default_factory=tuple)


def record_from_index(data: dict[str, Any]) -> PublicSearchRecord:
    languages = RelatedValues(
        PublicLanguage(
            iso_639_3_code=str(language.get("code", "")),
            name=str(language.get("name", "")),
            display_name=str(language.get("name", "")),
        )
        for language in data.get("languages", [])
    )
    location_data = data.get("location", {})
    general_info = PublicGeneralInfo(
        display_title=str(data.get("title", "")),
        description=str(data.get("description", "")),
        keywords=RelatedValues(
            PublicKeyword(str(value)) for value in data.get("keywords", [])
        ),
        object_languages=languages,
        location=PublicLocation(
            location_name=str(location_data.get("name", "")),
            country_name=str(location_data.get("country", "")),
            country_facet=str(location_data.get("country", "")),
            region_facet=str(location_data.get("region", "")),
            geo_location=str(location_data.get("geo", "")),
        ),
    )
    publication = data.get("publication", {})
    publication_info = PublicPublicationInfo(
        publication_year=publication.get("year"),
        data_provider=str(publication.get("provider", "")),
        creators=RelatedValues(
            _person_from_index(person) for person in publication.get("creators", [])
        ),
        contributors=RelatedValues(
            _person_from_index(person, contributor=True)
            for person in publication.get("contributors", [])
        ),
    )

    collection_data = data.get("collection")
    structural_info = None
    if isinstance(collection_data, dict):
        parent_general_info = PublicGeneralInfo(
            display_title=str(collection_data.get("title", "")),
            description="",
            keywords=RelatedValues(),
            object_languages=RelatedValues(),
            location=PublicLocation("", "", "", "", ""),
        )
        structural_info = PublicStructuralInfo(
            is_member_of_collection=PublicCollectionReference(
                identifier=str(collection_data.get("identifier", "")),
                handle_path=str(collection_data.get("handle_path", "")),
                get_general_info=parent_general_info,
            ),
        )

    return PublicSearchRecord(
        identifier=str(data.get("identifier", "")),
        handle_path=str(data.get("handle_path", "")),
        get_general_info=general_info,
        get_publication_info=publication_info,
        acl_access_level=str(data.get("acl_access_level", "")),
        bundles_count=int(data.get("bundles_count", 0)),
        get_structural_info=structural_info,
    )


def _person_from_index(
    data: dict[str, Any],
    *,
    contributor: bool = False,
) -> PublicPerson:
    family_name = str(data.get("family_name", ""))
    given_name = str(data.get("given_name", ""))
    contributor_name = None
    if contributor:
        contributor_name = PublicContributorName(family_name, given_name)
    return PublicPerson(
        family_name=family_name,
        given_name=given_name,
        contributor_display_name=str(data.get("display_name", "")),
        role=str(data.get("role", "")),
        contributor_name=contributor_name,
    )
