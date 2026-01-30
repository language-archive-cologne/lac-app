from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from xsdata.models.datatype import XmlDate, XmlPeriod

__NAMESPACE__ = "http://www.clarin.eu/cmd/"


class CollectionHasCollectionMemberIdentifierType(Enum):
    DOI = "DOI"
    HANDLE = "Handle"


class CollectionIdIdentifierType(Enum):
    DOI = "DOI"
    HANDLE = "Handle"
    URN = "URN"
    OTHER = "Other"


class ContributorNameIdentifierIdentifierType(Enum):
    ORCID = "ORCID"
    ISNI = "ISNI"
    EMAIL = "Email"
    OTHER = "Other"


class CreatorNameIdentifierIdentifierType(Enum):
    ORCID = "ORCID"
    ISNI = "ISNI"
    EMAIL = "Email"
    OTHER = "Other"


class FunderIdentifierIdentifierType(Enum):
    CROSSREF_FUNDER = "CrossrefFunder"
    ISNI = "ISNI"
    GRID = "GRID"
    OTHER = "Other"


class ResourcetypeSimple(Enum):
    """
    :cvar METADATA: The ResourceProxy refers to another component
        metadata instance (e.g. for grouping metadata descriptions into
        collections)
    :cvar RESOURCE: The ResourceProxy refers to a file that is not a
        metadata instance (e.g. a text document)
    :cvar SEARCH_SERVICE: The ResourceProxy refers to a (SRU/CQL) web
        service that can be used to query the resource described in this
        file
    :cvar SEARCH_PAGE: The ResourceProxy refers to a web page that can
        be used to query the resource described in this file
    :cvar LANDING_PAGE: The ResourceProxy refers to a web page that
        contains the "original context" of the resource described in
        this file (e.g. repository web page displaying the metadata).
    """

    METADATA = "Metadata"
    RESOURCE = "Resource"
    SEARCH_SERVICE = "SearchService"
    SEARCH_PAGE = "SearchPage"
    LANDING_PAGE = "LandingPage"


class RightsHolderIdentifierIdentifierType(Enum):
    ORCID = "ORCID"
    ISNI = "ISNI"
    EMAIL = "Email"
    OTHER = "Other"


@dataclass
class ComplextypeCollectionCountryCode611:
    class Meta:
        name = "complextype-CollectionCountryCode-6-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[A-Z]{2}",
        },
    )


@dataclass
class ComplextypeObjectLanguageGlottologCode0511:
    class Meta:
        name = "complextype-ObjectLanguageGlottologCode-0-5-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{4}[0-9]{4}",
        },
    )


@dataclass
class ComplextypeObjectLanguageIso6393Code0511:
    class Meta:
        name = "complextype-ObjectLanguageISO639-3Code-0-5-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{3}",
        },
    )


class SimpletypeAccess41(Enum):
    PUBLIC = "public"
    ACADEMIC = "academic"
    RESTRICTED = "restricted"


@dataclass
class ComplextypeAccess41:
    class Meta:
        name = "complextype-Access-4-1---"

    value: Optional[SimpletypeAccess41] = field(
        default=None,
        metadata={
            "required": True,
        },
    )


@dataclass
class Cmd:
    class Meta:
        name = "CMD"
        namespace = "http://www.clarin.eu/cmd/"

    header: Optional["Cmd.Header"] = field(
        default=None,
        metadata={
            "name": "Header",
            "type": "Element",
            "required": True,
        },
    )
    resources: Optional["Cmd.Resources"] = field(
        default=None,
        metadata={
            "name": "Resources",
            "type": "Element",
            "required": True,
        },
    )
    components: Optional["Cmd.Components"] = field(
        default=None,
        metadata={
            "name": "Components",
            "type": "Element",
            "required": True,
        },
    )
    cmdversion: str = field(
        init=False,
        default="1.1",
        metadata={
            "name": "CMDVersion",
            "type": "Attribute",
            "required": True,
        },
    )
    other_attributes: dict[str, str] = field(
        default_factory=dict,
        metadata={
            "type": "Attributes",
            "namespace": "##other",
        },
    )

    @dataclass
    class Header:
        md_creator: list["Cmd.Header.MdCreator"] = field(
            default_factory=list,
            metadata={
                "name": "MdCreator",
                "type": "Element",
            },
        )
        md_creation_date: Optional["Cmd.Header.MdCreationDate"] = field(
            default=None,
            metadata={
                "name": "MdCreationDate",
                "type": "Element",
            },
        )
        md_self_link: Optional["Cmd.Header.MdSelfLink"] = field(
            default=None,
            metadata={
                "name": "MdSelfLink",
                "type": "Element",
            },
        )
        md_profile: Optional["Cmd.Header.MdProfile"] = field(
            default=None,
            metadata={
                "name": "MdProfile",
                "type": "Element",
            },
        )
        md_collection_display_name: Optional[
            "Cmd.Header.MdCollectionDisplayName"
        ] = field(
            default=None,
            metadata={
                "name": "MdCollectionDisplayName",
                "type": "Element",
            },
        )
        other_attributes: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "type": "Attributes",
                "namespace": "##other",
            },
        )

        @dataclass
        class MdCreator:
            value: str = field(
                default="",
                metadata={
                    "required": True,
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

        @dataclass
        class MdCreationDate:
            value: Optional[XmlDate] = field(
                default=None,
                metadata={
                    "required": True,
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

        @dataclass
        class MdSelfLink:
            value: str = field(
                default="",
                metadata={
                    "required": True,
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

        @dataclass
        class MdProfile:
            value: str = field(
                default="",
                metadata={
                    "required": True,
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

        @dataclass
        class MdCollectionDisplayName:
            value: str = field(
                default="",
                metadata={
                    "required": True,
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

    @dataclass
    class Resources:
        resource_proxy_list: Optional["Cmd.Resources.ResourceProxyList"] = (
            field(
                default=None,
                metadata={
                    "name": "ResourceProxyList",
                    "type": "Element",
                    "required": True,
                },
            )
        )
        journal_file_proxy_list: Optional[
            "Cmd.Resources.JournalFileProxyList"
        ] = field(
            default=None,
            metadata={
                "name": "JournalFileProxyList",
                "type": "Element",
                "required": True,
            },
        )
        resource_relation_list: Optional[
            "Cmd.Resources.ResourceRelationList"
        ] = field(
            default=None,
            metadata={
                "name": "ResourceRelationList",
                "type": "Element",
                "required": True,
            },
        )
        is_part_of_list: Optional["Cmd.Resources.IsPartOfList"] = field(
            default=None,
            metadata={
                "name": "IsPartOfList",
                "type": "Element",
            },
        )
        other_attributes: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "type": "Attributes",
                "namespace": "##other",
            },
        )

        @dataclass
        class ResourceProxyList:
            resource_proxy: list[
                "Cmd.Resources.ResourceProxyList.ResourceProxy"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "ResourceProxy",
                    "type": "Element",
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

            @dataclass
            class ResourceProxy:
                resource_type: Optional[
                    "Cmd.Resources.ResourceProxyList.ResourceProxy.ResourceType"
                ] = field(
                    default=None,
                    metadata={
                        "name": "ResourceType",
                        "type": "Element",
                        "required": True,
                    },
                )
                resource_ref: Optional[
                    "Cmd.Resources.ResourceProxyList.ResourceProxy.ResourceRef"
                ] = field(
                    default=None,
                    metadata={
                        "name": "ResourceRef",
                        "type": "Element",
                        "required": True,
                    },
                )
                id: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "required": True,
                    },
                )
                other_attributes: dict[str, str] = field(
                    default_factory=dict,
                    metadata={
                        "type": "Attributes",
                        "namespace": "##other",
                    },
                )

                @dataclass
                class ResourceType:
                    value: Optional[ResourcetypeSimple] = field(
                        default=None,
                        metadata={
                            "required": True,
                        },
                    )
                    mimetype: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

                @dataclass
                class ResourceRef:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

        @dataclass
        class JournalFileProxyList:
            journal_file_proxy: list[
                "Cmd.Resources.JournalFileProxyList.JournalFileProxy"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "JournalFileProxy",
                    "type": "Element",
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

            @dataclass
            class JournalFileProxy:
                journal_file_ref: Optional[
                    "Cmd.Resources.JournalFileProxyList.JournalFileProxy.JournalFileRef"
                ] = field(
                    default=None,
                    metadata={
                        "name": "JournalFileRef",
                        "type": "Element",
                        "required": True,
                    },
                )
                other_attributes: dict[str, str] = field(
                    default_factory=dict,
                    metadata={
                        "type": "Attributes",
                        "namespace": "##other",
                    },
                )

                @dataclass
                class JournalFileRef:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

        @dataclass
        class ResourceRelationList:
            resource_relation: list[
                "Cmd.Resources.ResourceRelationList.ResourceRelation"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "ResourceRelation",
                    "type": "Element",
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

            @dataclass
            class ResourceRelation:
                relation_type: Optional[
                    "Cmd.Resources.ResourceRelationList.ResourceRelation.RelationType"
                ] = field(
                    default=None,
                    metadata={
                        "name": "RelationType",
                        "type": "Element",
                        "required": True,
                    },
                )
                res1: Optional[
                    "Cmd.Resources.ResourceRelationList.ResourceRelation.Res1"
                ] = field(
                    default=None,
                    metadata={
                        "name": "Res1",
                        "type": "Element",
                        "required": True,
                    },
                )
                res2: Optional[
                    "Cmd.Resources.ResourceRelationList.ResourceRelation.Res2"
                ] = field(
                    default=None,
                    metadata={
                        "name": "Res2",
                        "type": "Element",
                        "required": True,
                    },
                )
                other_attributes: dict[str, str] = field(
                    default_factory=dict,
                    metadata={
                        "type": "Attributes",
                        "namespace": "##other",
                    },
                )

                @dataclass
                class RelationType:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

                @dataclass
                class Res1:
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

                @dataclass
                class Res2:
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##other",
                        },
                    )

        @dataclass
        class IsPartOfList:
            is_part_of: list["Cmd.Resources.IsPartOfList.IsPartOf"] = field(
                default_factory=list,
                metadata={
                    "name": "IsPartOf",
                    "type": "Element",
                },
            )
            other_attributes: dict[str, str] = field(
                default_factory=dict,
                metadata={
                    "type": "Attributes",
                    "namespace": "##other",
                },
            )

            @dataclass
            class IsPartOf:
                value: str = field(
                    default="",
                    metadata={
                        "required": True,
                    },
                )
                other_attributes: dict[str, str] = field(
                    default_factory=dict,
                    metadata={
                        "type": "Attributes",
                        "namespace": "##other",
                    },
                )

    @dataclass
    class Components:
        blam_collection_repository_v1_2: Optional[
            "Cmd.Components.BlamCollectionRepositoryV12"
        ] = field(
            default=None,
            metadata={
                "name": "BLAM-collection-repository_v1.2",
                "type": "Element",
                "required": True,
            },
        )
        other_attributes: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "type": "Attributes",
                "namespace": "##other",
            },
        )

        @dataclass
        class BlamCollectionRepositoryV12:
            mdlicense: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.Mdlicense"
            ] = field(
                default=None,
                metadata={
                    "name": "MDLicense",
                    "type": "Element",
                    "required": True,
                },
            )
            collection_general_info: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "CollectionGeneralInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            collection_publication_info: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "CollectionPublicationInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            project_info: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.ProjectInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "ProjectInfo",
                    "type": "Element",
                },
            )
            collection_administrative_info: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "CollectionAdministrativeInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            collection_structural_info: Optional[
                "Cmd.Components.BlamCollectionRepositoryV12.CollectionStructuralInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "CollectionStructuralInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            ref: list[str] = field(
                default_factory=list,
                metadata={
                    "type": "Attribute",
                    "tokens": True,
                },
            )

            @dataclass
            class Mdlicense:
                value: str = field(
                    default="",
                    metadata={
                        "required": True,
                    },
                )
                uri: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "URI",
                        "type": "Attribute",
                    },
                )

            @dataclass
            class CollectionGeneralInfo:
                collection_id: list[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionId"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "CollectionID",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                collection_version: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "CollectionVersion",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_display_title: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "CollectionDisplayTitle",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_description: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "CollectionDescription",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_keywords: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionKeywords"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionKeywords",
                        "type": "Element",
                    },
                )
                collection_object_languages: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionObjectLanguages"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionObjectLanguages",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_location: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionLocation"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionLocation",
                        "type": "Element",
                        "required": True,
                    },
                )
                ref: list[str] = field(
                    default_factory=list,
                    metadata={
                        "type": "Attribute",
                        "tokens": True,
                    },
                )

                @dataclass
                class CollectionId:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    identifier_type: Optional[CollectionIdIdentifierType] = (
                        field(
                            default=None,
                            metadata={
                                "name": "IdentifierType",
                                "type": "Attribute",
                            },
                        )
                    )

                @dataclass
                class CollectionKeywords:
                    collection_keyword: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "CollectionKeyword",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                @dataclass
                class CollectionObjectLanguages:
                    collection_object_language: list[
                        "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "CollectionObjectLanguage",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class CollectionObjectLanguage:
                        object_language_display_name: list[str] = field(
                            default_factory=list,
                            metadata={
                                "name": "ObjectLanguageDisplayName",
                                "type": "Element",
                                "min_occurs": 1,
                            },
                        )
                        object_language_name: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageName",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        object_language_iso639_3_code: Optional[
                            ComplextypeObjectLanguageIso6393Code0511
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageISO639-3Code",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        object_language_glottolog_code: Optional[
                            ComplextypeObjectLanguageGlottologCode0511
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageGlottologCode",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        object_language_alternative_names: Optional[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageAlternativeNames"
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageAlternativeNames",
                                "type": "Element",
                            },
                        )
                        object_language_taxonomy: Optional[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageTaxonomy"
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageTaxonomy",
                                "type": "Element",
                            },
                        )
                        ref: list[str] = field(
                            default_factory=list,
                            metadata={
                                "type": "Attribute",
                                "tokens": True,
                            },
                        )

                        @dataclass
                        class ObjectLanguageAlternativeNames:
                            object_language_alternative_name: list[str] = (
                                field(
                                    default_factory=list,
                                    metadata={
                                        "name": "ObjectLanguageAlternativeName",
                                        "type": "Element",
                                    },
                                )
                            )
                            ref: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "type": "Attribute",
                                    "tokens": True,
                                },
                            )

                        @dataclass
                        class ObjectLanguageTaxonomy:
                            object_language_language_family: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "name": "ObjectLanguageLanguageFamily",
                                    "type": "Element",
                                    "min_occurs": 1,
                                },
                            )
                            ref: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "type": "Attribute",
                                    "tokens": True,
                                },
                            )

                @dataclass
                class CollectionLocation:
                    collection_geo_location: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionGeoLocation",
                            "type": "Element",
                        },
                    )
                    collection_location_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionLocationName",
                            "type": "Element",
                        },
                    )
                    collection_location_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionLocationFacet",
                            "type": "Element",
                        },
                    )
                    collection_region_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionRegionName",
                            "type": "Element",
                        },
                    )
                    collection_region_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionRegionFacet",
                            "type": "Element",
                        },
                    )
                    collection_country_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionCountryName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    collection_country_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "CollectionCountryFacet",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    collection_country_code: Optional[
                        ComplextypeCollectionCountryCode611
                    ] = field(
                        default=None,
                        metadata={
                            "name": "CollectionCountryCode",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

            @dataclass
            class CollectionPublicationInfo:
                collection_publication_year: Optional[XmlPeriod] = field(
                    default=None,
                    metadata={
                        "name": "CollectionPublicationYear",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_data_provider: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "CollectionDataProvider",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_creators: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionCreators",
                        "type": "Element",
                        "required": True,
                    },
                )
                collection_contributors: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionContributors",
                        "type": "Element",
                    },
                )
                ref: list[str] = field(
                    default_factory=list,
                    metadata={
                        "type": "Attribute",
                        "tokens": True,
                    },
                )

                @dataclass
                class CollectionCreators:
                    collection_creator: list[
                        "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "CollectionCreator",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class CollectionCreator:
                        creator_name_identifier: list[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorNameIdentifier"
                        ] = field(
                            default_factory=list,
                            metadata={
                                "name": "CreatorNameIdentifier",
                                "type": "Element",
                            },
                        )
                        creator_affiliation: list[str] = field(
                            default_factory=list,
                            metadata={
                                "name": "CreatorAffiliation",
                                "type": "Element",
                            },
                        )
                        creator_name: Optional[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorName"
                        ] = field(
                            default=None,
                            metadata={
                                "name": "CreatorName",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        ref: list[str] = field(
                            default_factory=list,
                            metadata={
                                "type": "Attribute",
                                "tokens": True,
                            },
                        )
                        order: Optional[int] = field(
                            default=None,
                            metadata={
                                "name": "Order",
                                "type": "Attribute",
                            },
                        )

                        @dataclass
                        class CreatorNameIdentifier:
                            value: str = field(
                                default="",
                                metadata={
                                    "required": True,
                                },
                            )
                            identifier_type: Optional[
                                CreatorNameIdentifierIdentifierType
                            ] = field(
                                default=None,
                                metadata={
                                    "name": "IdentifierType",
                                    "type": "Attribute",
                                },
                            )

                        @dataclass
                        class CreatorName:
                            creator_family_name: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "CreatorFamilyName",
                                    "type": "Element",
                                    "required": True,
                                },
                            )
                            creator_given_name: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "CreatorGivenName",
                                    "type": "Element",
                                },
                            )
                            ref: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "type": "Attribute",
                                    "tokens": True,
                                },
                            )

                @dataclass
                class CollectionContributors:
                    collection_contributor: list[
                        "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "CollectionContributor",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class CollectionContributor:
                        contributor_name_identifier: list[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorNameIdentifier"
                        ] = field(
                            default_factory=list,
                            metadata={
                                "name": "ContributorNameIdentifier",
                                "type": "Element",
                            },
                        )
                        contributor_affiliation: list[str] = field(
                            default_factory=list,
                            metadata={
                                "name": "ContributorAffiliation",
                                "type": "Element",
                            },
                        )
                        contributor_role: list[str] = field(
                            default_factory=list,
                            metadata={
                                "name": "ContributorRole",
                                "type": "Element",
                            },
                        )
                        contributor_name: Optional[
                            "Cmd.Components.BlamCollectionRepositoryV12.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorName"
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ContributorName",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        ref: list[str] = field(
                            default_factory=list,
                            metadata={
                                "type": "Attribute",
                                "tokens": True,
                            },
                        )

                        @dataclass
                        class ContributorNameIdentifier:
                            value: str = field(
                                default="",
                                metadata={
                                    "required": True,
                                },
                            )
                            identifier_type: Optional[
                                ContributorNameIdentifierIdentifierType
                            ] = field(
                                default=None,
                                metadata={
                                    "name": "IdentifierType",
                                    "type": "Attribute",
                                },
                            )

                        @dataclass
                        class ContributorName:
                            contributor_family_name: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "ContributorFamilyName",
                                    "type": "Element",
                                    "required": True,
                                },
                            )
                            contributor_given_name: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "ContributorGivenName",
                                    "type": "Element",
                                },
                            )
                            ref: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "type": "Attribute",
                                    "tokens": True,
                                },
                            )

            @dataclass
            class ProjectInfo:
                project: list[
                    "Cmd.Components.BlamCollectionRepositoryV12.ProjectInfo.Project"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "Project",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                ref: list[str] = field(
                    default_factory=list,
                    metadata={
                        "type": "Attribute",
                        "tokens": True,
                    },
                )

                @dataclass
                class Project:
                    project_display_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "ProjectDisplayName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    project_description: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "ProjectDescription",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    funder_infos: Optional[
                        "Cmd.Components.BlamCollectionRepositoryV12.ProjectInfo.Project.FunderInfos"
                    ] = field(
                        default=None,
                        metadata={
                            "name": "FunderInfos",
                            "type": "Element",
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class FunderInfos:
                        funder_info: list[
                            "Cmd.Components.BlamCollectionRepositoryV12.ProjectInfo.Project.FunderInfos.FunderInfo"
                        ] = field(
                            default_factory=list,
                            metadata={
                                "name": "FunderInfo",
                                "type": "Element",
                                "min_occurs": 1,
                            },
                        )
                        ref: list[str] = field(
                            default_factory=list,
                            metadata={
                                "type": "Attribute",
                                "tokens": True,
                            },
                        )

                        @dataclass
                        class FunderInfo:
                            funder_name: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "FunderName",
                                    "type": "Element",
                                    "required": True,
                                },
                            )
                            funder_identifier: Optional[
                                "Cmd.Components.BlamCollectionRepositoryV12.ProjectInfo.Project.FunderInfos.FunderInfo.FunderIdentifier"
                            ] = field(
                                default=None,
                                metadata={
                                    "name": "FunderIdentifier",
                                    "type": "Element",
                                },
                            )
                            grant_identifier: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "GrantIdentifier",
                                    "type": "Element",
                                },
                            )
                            grant_uri: Optional[str] = field(
                                default=None,
                                metadata={
                                    "name": "GrantURI",
                                    "type": "Element",
                                },
                            )
                            ref: list[str] = field(
                                default_factory=list,
                                metadata={
                                    "type": "Attribute",
                                    "tokens": True,
                                },
                            )

                            @dataclass
                            class FunderIdentifier:
                                value: str = field(
                                    default="",
                                    metadata={
                                        "required": True,
                                    },
                                )
                                identifier_type: Optional[
                                    FunderIdentifierIdentifierType
                                ] = field(
                                    default=None,
                                    metadata={
                                        "name": "IdentifierType",
                                        "type": "Attribute",
                                    },
                                )

            @dataclass
            class CollectionAdministrativeInfo:
                collection_is_identical_to: list[str] = field(
                    default_factory=list,
                    metadata={
                        "name": "CollectionIsIdenticalTo",
                        "type": "Element",
                    },
                )
                collection_is_derivation_of: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "CollectionIsDerivationOf",
                        "type": "Element",
                    },
                )
                access: Optional[ComplextypeAccess41] = field(
                    default=None,
                    metadata={
                        "name": "Access",
                        "type": "Element",
                        "required": True,
                    },
                )
                availability_date: Optional[XmlDate] = field(
                    default=None,
                    metadata={
                        "name": "AvailabilityDate",
                        "type": "Element",
                        "required": True,
                    },
                )
                license: list[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.License"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "License",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                rights_holder: list[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.RightsHolder"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "RightsHolder",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                ref: list[str] = field(
                    default_factory=list,
                    metadata={
                        "type": "Attribute",
                        "tokens": True,
                    },
                )

                @dataclass
                class License:
                    license_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "LicenseName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    license_identifier: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "LicenseIdentifier",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                @dataclass
                class RightsHolder:
                    rights_holder_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "RightsHolderName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    rights_holder_identifier: list[
                        "Cmd.Components.BlamCollectionRepositoryV12.CollectionAdministrativeInfo.RightsHolder.RightsHolderIdentifier"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "RightsHolderIdentifier",
                            "type": "Element",
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class RightsHolderIdentifier:
                        value: str = field(
                            default="",
                            metadata={
                                "required": True,
                            },
                        )
                        identifier_type: Optional[
                            RightsHolderIdentifierIdentifierType
                        ] = field(
                            default=None,
                            metadata={
                                "name": "IdentifierType",
                                "type": "Attribute",
                            },
                        )

            @dataclass
            class CollectionStructuralInfo:
                collection_additional_metadata_file: list[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionStructuralInfo.CollectionAdditionalMetadataFile"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "CollectionAdditionalMetadataFile",
                        "type": "Element",
                    },
                )
                collection_members: Optional[
                    "Cmd.Components.BlamCollectionRepositoryV12.CollectionStructuralInfo.CollectionMembers"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CollectionMembers",
                        "type": "Element",
                        "required": True,
                    },
                )
                ref: list[str] = field(
                    default_factory=list,
                    metadata={
                        "type": "Attribute",
                        "tokens": True,
                    },
                )

                @dataclass
                class CollectionAdditionalMetadataFile:
                    file_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "FileName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    file_pid: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "FilePID",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    mime_type: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "MimeType",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    is_metadata_for: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "IsMetadataFor",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    file_description: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "FileDescription",
                            "type": "Element",
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                @dataclass
                class CollectionMembers:
                    collection_has_collection_member: list[
                        "Cmd.Components.BlamCollectionRepositoryV12.CollectionStructuralInfo.CollectionMembers.CollectionHasCollectionMember"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "CollectionHasCollectionMember",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    ref: list[str] = field(
                        default_factory=list,
                        metadata={
                            "type": "Attribute",
                            "tokens": True,
                        },
                    )

                    @dataclass
                    class CollectionHasCollectionMember:
                        value: str = field(
                            default="",
                            metadata={
                                "required": True,
                            },
                        )
                        identifier_type: Optional[
                            CollectionHasCollectionMemberIdentifierType
                        ] = field(
                            default=None,
                            metadata={
                                "name": "IdentifierType",
                                "type": "Attribute",
                            },
                        )
