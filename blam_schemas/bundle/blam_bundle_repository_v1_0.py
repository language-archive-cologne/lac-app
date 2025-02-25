from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from xsdata.models.datatype import XmlDate, XmlPeriod

__NAMESPACE__ = "http://www.clarin.eu/cmd/"


class BundleIdIdentifierType(Enum):
    DOI = "DOI"
    HANDLE = "Handle"
    URN = "URN"
    OTHER = "Other"


class BundleIsMemberOfCollectionIdentifierType(Enum):
    DOI = "DOI"
    HANDLE = "Handle"


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
class ComplextypeBundleCountryCode711:
    class Meta:
        name = "complextype-BundleCountryCode-7-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[A-Z]{2}",
        },
    )


@dataclass
class ComplextypeBundleRecordingDate11:
    class Meta:
        name = "complextype-BundleRecordingDate-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"([0-9]{4}(-(0[1-9]|1[012])(-([0-2][0-9]|3[01]))?)?)|Unknown",
        },
    )


@dataclass
class ComplextypeObjectLanguageGlottologCode0611:
    class Meta:
        name = "complextype-ObjectLanguageGlottologCode-0-6-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{4}[0-9]{4}",
        },
    )


@dataclass
class ComplextypeObjectLanguageIso6393Code0611:
    class Meta:
        name = "complextype-ObjectLanguageISO639-3Code-0-6-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{3}",
        },
    )


class SimpletypeAccess51(Enum):
    OPEN = "open"
    REGISTRATION_REQUIRED = "registration required"
    REQUEST_REQUIRED = "request required"


@dataclass
class ComplextypeAccess51:
    class Meta:
        name = "complextype-Access-5-1---"

    value: Optional[SimpletypeAccess51] = field(
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
        blam_bundle_repository_v1_0: Optional[
            "Cmd.Components.BlamBundleRepositoryV10"
        ] = field(
            default=None,
            metadata={
                "name": "BLAM-bundle-repository_v1.0",
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
        class BlamBundleRepositoryV10:
            mdlicense: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.Mdlicense"
            ] = field(
                default=None,
                metadata={
                    "name": "MDLicense",
                    "type": "Element",
                    "required": True,
                },
            )
            bundle_general_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "BundleGeneralInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            bundle_publication_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "BundlePublicationInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            project_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.ProjectInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "ProjectInfo",
                    "type": "Element",
                },
            )
            bundle_data_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "BundleDataInfo",
                    "type": "Element",
                },
            )
            bundle_administrative_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "BundleAdministrativeInfo",
                    "type": "Element",
                    "required": True,
                },
            )
            bundle_structural_info: Optional[
                "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo"
            ] = field(
                default=None,
                metadata={
                    "name": "BundleStructuralInfo",
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
            class BundleGeneralInfo:
                bundle_id: list[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleId"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "BundleID",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                bundle_version: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "BundleVersion",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_display_title: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "BundleDisplayTitle",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_description: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "BundleDescription",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_recording_date: Optional[
                    ComplextypeBundleRecordingDate11
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleRecordingDate",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_keywords: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleKeywords"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleKeywords",
                        "type": "Element",
                    },
                )
                bundle_object_languages: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleObjectLanguages",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_location: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleLocation"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleLocation",
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
                class BundleId:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    identifier_type: Optional[BundleIdIdentifierType] = field(
                        default=None,
                        metadata={
                            "name": "IdentifierType",
                            "type": "Attribute",
                        },
                    )

                @dataclass
                class BundleKeywords:
                    bundle_keyword: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "BundleKeyword",
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
                class BundleObjectLanguages:
                    bundle_object_language: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "BundleObjectLanguage",
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
                    class BundleObjectLanguage:
                        object_language_display_name: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageDisplayName",
                                "type": "Element",
                                "required": True,
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
                            ComplextypeObjectLanguageIso6393Code0611
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageISO639-3Code",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        object_language_glottolog_code: Optional[
                            ComplextypeObjectLanguageGlottologCode0611
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageGlottologCode",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        object_language_alternative_names: Optional[
                            "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageAlternativeNames"
                        ] = field(
                            default=None,
                            metadata={
                                "name": "ObjectLanguageAlternativeNames",
                                "type": "Element",
                            },
                        )
                        object_language_taxonomy: Optional[
                            "Cmd.Components.BlamBundleRepositoryV10.BundleGeneralInfo.BundleObjectLanguages.BundleObjectLanguage.ObjectLanguageTaxonomy"
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
                class BundleLocation:
                    bundle_geo_location: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleGeoLocation",
                            "type": "Element",
                        },
                    )
                    bundle_location_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleLocationName",
                            "type": "Element",
                        },
                    )
                    bundle_location_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleLocationFacet",
                            "type": "Element",
                        },
                    )
                    bundle_region_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleRegionName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    bundle_region_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleRegionFacet",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    bundle_country_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleCountryName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    bundle_country_facet: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "BundleCountryFacet",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    bundle_country_code: Optional[
                        ComplextypeBundleCountryCode711
                    ] = field(
                        default=None,
                        metadata={
                            "name": "BundleCountryCode",
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
            class BundlePublicationInfo:
                bundle_publication_year: Optional[XmlPeriod] = field(
                    default=None,
                    metadata={
                        "name": "BundlePublicationYear",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_data_provider: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "BundleDataProvider",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_creators: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleCreators",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_contributors: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleContributors",
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
                class BundleCreators:
                    bundle_creator: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "BundleCreator",
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
                    class BundleCreator:
                        creator_name_identifier: list[
                            "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorNameIdentifier"
                        ] = field(
                            default_factory=list,
                            metadata={
                                "name": "CreatorNameIdentifier",
                                "type": "Element",
                                "min_occurs": 1,
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
                            "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleCreators.BundleCreator.CreatorName"
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
                class BundleContributors:
                    bundle_contributor: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "BundleContributor",
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
                    class BundleContributor:
                        contributor_name_identifier: list[
                            "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorNameIdentifier"
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
                            "Cmd.Components.BlamBundleRepositoryV10.BundlePublicationInfo.BundleContributors.BundleContributor.ContributorName"
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
                    "Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project"
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
                        "Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos"
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
                            "Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo"
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
                            funder_identifier: list[
                                "Cmd.Components.BlamBundleRepositoryV10.ProjectInfo.Project.FunderInfos.FunderInfo.FunderIdentifier"
                            ] = field(
                                default_factory=list,
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
            class BundleDataInfo:
                segmentation_units: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.SegmentationUnits"
                ] = field(
                    default=None,
                    metadata={
                        "name": "SegmentationUnits",
                        "type": "Element",
                    },
                )
                transcription_types: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranscriptionTypes"
                ] = field(
                    default=None,
                    metadata={
                        "name": "TranscriptionTypes",
                        "type": "Element",
                    },
                )
                translation_languages: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranslationLanguages"
                ] = field(
                    default=None,
                    metadata={
                        "name": "TranslationLanguages",
                        "type": "Element",
                    },
                )
                annotation_types: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.AnnotationTypes"
                ] = field(
                    default=None,
                    metadata={
                        "name": "AnnotationTypes",
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
                class SegmentationUnits:
                    segmentation_unit: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "SegmentationUnit",
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
                class TranscriptionTypes:
                    transcription_type: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "TranscriptionType",
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
                class TranslationLanguages:
                    translation_language: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundleDataInfo.TranslationLanguages.TranslationLanguage"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "TranslationLanguage",
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
                    class TranslationLanguage:
                        translation_language_name: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "TranslationLanguageName",
                                "type": "Element",
                                "required": True,
                            },
                        )
                        translation_language_code: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "TranslationLanguageCode",
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
                class AnnotationTypes:
                    annotation_type: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "AnnotationType",
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
            class BundleAdministrativeInfo:
                bundle_is_identical_to: list[str] = field(
                    default_factory=list,
                    metadata={
                        "name": "BundleIsIdenticalTo",
                        "type": "Element",
                    },
                )
                bundle_is_derivation_of: Optional[str] = field(
                    default=None,
                    metadata={
                        "name": "BundleIsDerivationOf",
                        "type": "Element",
                    },
                )
                access: Optional[ComplextypeAccess51] = field(
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
                    "Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.License"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "License",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                rights_holder: list[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder"
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
                        "Cmd.Components.BlamBundleRepositoryV10.BundleAdministrativeInfo.RightsHolder.RightsHolderIdentifier"
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
            class BundleStructuralInfo:
                bundle_is_member_of_collection: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleIsMemberOfCollection"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleIsMemberOfCollection",
                        "type": "Element",
                        "required": True,
                    },
                )
                bundle_additional_metadata_file: list[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleAdditionalMetadataFile"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "BundleAdditionalMetadataFile",
                        "type": "Element",
                    },
                )
                bundle_resources: Optional[
                    "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources"
                ] = field(
                    default=None,
                    metadata={
                        "name": "BundleResources",
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
                class BundleIsMemberOfCollection:
                    value: str = field(
                        default="",
                        metadata={
                            "required": True,
                        },
                    )
                    identifier_type: Optional[
                        BundleIsMemberOfCollectionIdentifierType
                    ] = field(
                        default=None,
                        metadata={
                            "name": "IdentifierType",
                            "type": "Attribute",
                        },
                    )

                @dataclass
                class BundleAdditionalMetadataFile:
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
                class BundleResources:
                    media_resource: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.MediaResource"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "MediaResource",
                            "type": "Element",
                        },
                    )
                    written_resource: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.WrittenResource"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "WrittenResource",
                            "type": "Element",
                        },
                    )
                    other_resource: list[
                        "Cmd.Components.BlamBundleRepositoryV10.BundleStructuralInfo.BundleResources.OtherResource"
                    ] = field(
                        default_factory=list,
                        metadata={
                            "name": "OtherResource",
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
                    class MediaResource:
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
                        file_length: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "FileLength",
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
                    class WrittenResource:
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
                        is_annotation_of: list[str] = field(
                            default_factory=list,
                            metadata={
                                "name": "IsAnnotationOf",
                                "type": "Element",
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
                    class OtherResource:
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
