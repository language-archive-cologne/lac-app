from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from xsdata.models.datatype import XmlDate

__NAMESPACE__ = "http://www.clarin.eu/cmd/"


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
    is_part_of_list: Optional["Cmd.IsPartOfList"] = field(
        default=None,
        metadata={
            "name": "IsPartOfList",
            "type": "Element",
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
    cmdversion: str | None = field(
        default=None,
        metadata={
            "name": "CMDVersion",
            "type": "Attribute",
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
                "required": True,
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
                    "namespace": "##any",
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
                    "namespace": "##any",
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
                    "namespace": "##any",
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
                    "namespace": "##any",
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
                    "namespace": "##any",
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
        other_attributes: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "type": "Attributes",
                "namespace": "##any",
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
                    "namespace": "##any",
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
                        "namespace": "##any",
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
                            "namespace": "##any",
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
                            "namespace": "##any",
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
                    "namespace": "##any",
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
                        "namespace": "##any",
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
                            "namespace": "##any",
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
                    "namespace": "##any",
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
                resource: list[
                    "Cmd.Resources.ResourceRelationList.ResourceRelation.Resource"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "Resource",
                        "type": "Element",
                        "min_occurs": 2,
                        "max_occurs": 2,
                    },
                )
                other_attributes: dict[str, str] = field(
                    default_factory=dict,
                    metadata={
                        "type": "Attributes",
                        "namespace": "##any",
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
                    concept_link: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "ConceptLink",
                            "type": "Attribute",
                        },
                    )
                    other_attributes: dict[str, str] = field(
                        default_factory=dict,
                        metadata={
                            "type": "Attributes",
                            "namespace": "##any",
                        },
                    )

                @dataclass
                class Resource:
                    role: Optional[
                        "Cmd.Resources.ResourceRelationList.ResourceRelation.Resource.Role"
                    ] = field(
                        default=None,
                        metadata={
                            "name": "Role",
                            "type": "Element",
                        },
                    )
                    ref: Optional[str] = field(
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
                            "namespace": "##any",
                        },
                    )

                    @dataclass
                    class Role:
                        value: str = field(
                            default="",
                            metadata={
                                "required": True,
                            },
                        )
                        concept_link: Optional[str] = field(
                            default=None,
                            metadata={
                                "name": "ConceptLink",
                                "type": "Attribute",
                            },
                        )
                        other_attributes: dict[str, str] = field(
                            default_factory=dict,
                            metadata={
                                "type": "Attributes",
                                "namespace": "##any",
                            },
                        )

    @dataclass
    class IsPartOfList:
        is_part_of: list["Cmd.IsPartOfList.IsPartOf"] = field(
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
                "namespace": "##any",
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
                    "namespace": "##any",
                },
            )

    @dataclass
    class Components:
        other_element: Optional[object] = field(
            default=None,
            metadata={
                "type": "Wildcard",
                "namespace": "##any",
            },
        )
        other_attributes: dict[str, str] = field(
            default_factory=dict,
            metadata={
                "type": "Attributes",
                "namespace": "##any",
            },
        )
