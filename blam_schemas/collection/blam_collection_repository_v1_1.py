from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from xsdata.models.datatype import XmlDate, XmlPeriod

__NAMESPACE__ = (
    "http://www.clarin.eu/cmd/"
)


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


class RightsHolderIdentifierIdentifierType(Enum):
    ORCID = "ORCID"
    ISNI = "ISNI"
    EMAIL = "Email"
    OTHER = "Other"


@dataclass
class ComplextypeCollectionCountryCode711:
    class Meta:
        name = "complextype-CollectionCountryCode-7-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[A-Z]{2}",
        },
    )


@dataclass
class ComplextypeObjectLanguageGlottologCode1611:
    class Meta:
        name = "complextype-ObjectLanguageGlottologCode-1-6-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{4}[0-9]{4}",
        },
    )


@dataclass
class ComplextypeObjectLanguageIso6393Code1611:
    class Meta:
        name = "complextype-ObjectLanguageISO639-3Code-1-6-1-1---"

    value: str = field(
        default="",
        metadata={
            "required": True,
            "pattern": r"[a-z]{3}",
        },
    )


class SimpletypeAccess41(Enum):
    OPEN = "open"
    REGISTRATION_REQUIRED = "registration required"
    REQUEST_REQUIRED = "request required"


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
class BlamCollectionRepositoryV11:
    """
    :ivar mdlicense: The MDLicense element contains information about
        the license under which the metadata is made available.
    :ivar collection_general_info: CollectionGeneralInfo contains
        general descriptive metadata about the collection.
    :ivar collection_publication_info: The CollectionPublicationInfo
        component contains metadata pertaining the publication of the
        resource. The information provided in this component is used in
        the interface of the repository and in particular to generate
        bibliographical references to the resource.
    :ivar project_info: ProjectInfo contains descriptive information
        about the project or the projects relating to the resource.
    :ivar collection_administrative_info: CollectionAdministrativeInfo
        contains administrative metadata that will be publicly
        communicated, especially in regard to metacatalogues and user
        interfaces.
    :ivar collection_structural_info: CollectionStructuralInfo contains
        structural metadata that describes the internal structure of the
        collection.
    :ivar base:
    :ivar ref:
    """

    class Meta:
        name = "BLAM-collection-repository_v1.1"
        namespace = (
            "http://www.clarin.eu/cmd/"
        )

    mdlicense: Optional["BlamCollectionRepositoryV11.Mdlicense"] = field(
        default=None,
        metadata={
            "name": "MDLicense",
            "type": "Element",
            "required": True,
        },
    )
    collection_general_info: Optional[
        "BlamCollectionRepositoryV11.CollectionGeneralInfo"
    ] = field(
        default=None,
        metadata={
            "name": "CollectionGeneralInfo",
            "type": "Element",
            "required": True,
        },
    )
    collection_publication_info: Optional[
        "BlamCollectionRepositoryV11.CollectionPublicationInfo"
    ] = field(
        default=None,
        metadata={
            "name": "CollectionPublicationInfo",
            "type": "Element",
            "required": True,
        },
    )
    project_info: Optional["BlamCollectionRepositoryV11.ProjectInfo"] = field(
        default=None,
        metadata={
            "name": "ProjectInfo",
            "type": "Element",
        },
    )
    collection_administrative_info: Optional[
        "BlamCollectionRepositoryV11.CollectionAdministrativeInfo"
    ] = field(
        default=None,
        metadata={
            "name": "CollectionAdministrativeInfo",
            "type": "Element",
            "required": True,
        },
    )
    collection_structural_info: Optional[
        "BlamCollectionRepositoryV11.CollectionStructuralInfo"
    ] = field(
        default=None,
        metadata={
            "name": "CollectionStructuralInfo",
            "type": "Element",
            "required": True,
        },
    )
    base: Optional[str] = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.w3.org/XML/1998/namespace",
        },
    )
    ref: Optional[str] = field(
        default=None,
        metadata={
            "type": "Attribute",
            "namespace": "http://www.clarin.eu/cmd/1",
        },
    )

    @dataclass
    class Mdlicense:
        """
        :ivar value:
        :ivar uri: The URI of the license.
        """

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
                "required": True,
            },
        )

    @dataclass
    class CollectionGeneralInfo:
        """
        :ivar collection_id: The CollectionID element contains an
            identifier that consistently and uniquely identifies the
            collection described in the particular metadata token. The
            identifier should be generated by the repository during the
            initialization process.
        :ivar collection_version: CollectionVersion contains the version
            number of the collection.
        :ivar collection_display_title: The CollectionDisplayTitle
            element provides a human readable name of the collection. It
            should contain a meaningful and recognisable title for the
            collection. The content of the CollectionDisplayTitle
            element will be used as the human readable identifier in
            interfaces. Data producers can provide
            CollectionDisplayTitle values for multiple interface
            languages. This field will be used as the human readable
            identifier for the collection in citation and interfaces.
        :ivar collection_description: The CollectionDescription element
            provides a human readable description of the collection. It
            should contain a description of the content of the
            collection. The content of the CollectionDescription element
            will be used as the human readable description in
            interfaces. Its content can be queried by repositories for
            free-text metadata search.
        :ivar collection_keywords: CollectionKeywords should be used to
            describe the content and nature of data to enhance the
            discoverability and facilitate finer granularity for
            searches and browsing of the data.
        :ivar collection_object_languages: CollectionObjectLanguages
            contains information about the language or languages that
            are the object of the resource.
        :ivar collection_location: CollectionLocation contains
            information about the most relevant or salient location in
            relation to the data contained in the collection. The
            default location would be the main location of recording.
            However, any other location viewed as most relevant to the
            data can be set as the CollectionLocation. The information
            provided in the component is intended for discoverability
            and display purposes. Detailed documentation of geographic
            information should be outsourced into an additional metadata
            file.
        :ivar base:
        :ivar ref:
        """

        collection_id: list[
            "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionId"
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
            "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionKeywords"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionKeywords",
                "type": "Element",
            },
        )
        collection_object_languages: Optional[
            "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionObjectLanguages"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionObjectLanguages",
                "type": "Element",
                "required": True,
            },
        )
        collection_location: Optional[
            "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionLocation"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionLocation",
                "type": "Element",
                "required": True,
            },
        )
        base: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )
        ref: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.clarin.eu/cmd/1",
            },
        )

        @dataclass
        class CollectionId:
            """
            :ivar value:
            :ivar identifier_type: The IdentifierType attribute
                determines the identifier type used. Recommended
                practice is to have a DOI and a Handle for each
                collection.
            """

            value: str = field(
                default="",
                metadata={
                    "required": True,
                },
            )
            identifier_type: Optional[CollectionIdIdentifierType] = field(
                default=None,
                metadata={
                    "name": "IdentifierType",
                    "type": "Attribute",
                    "required": True,
                },
            )

        @dataclass
        class CollectionKeywords:
            """
            :ivar collection_keyword: CollectionKeyword should contain a
                single keyword or a keyphrase and should be used to
                describe the content and nature of data to enhance the
                discoverability and facilitate finer granularity for
                searches and browsing of the data.
            :ivar base:
            :ivar ref:
            """

            collection_keyword: list[str] = field(
                default_factory=list,
                metadata={
                    "name": "CollectionKeyword",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

        @dataclass
        class CollectionObjectLanguages:
            """
            :ivar collection_object_language: CollectionObjectLanguage
                contains information about the language that is the
                object of the resource.
            :ivar base:
            :ivar ref:
            """

            collection_object_language: list[
                "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "CollectionObjectLanguage",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class CollectionObjectLanguage:
                """
                :ivar object_language_display_name: The
                    ObjectLanguageDisplayName element contains the name
                    of the object language in the version recommended by
                    the data producer. Repositories should treat the
                    name provided by this element as the primary
                    language name when displaying the metadata in
                    relation to this particular data set. The repository
                    may use alternative names provided by services such
                    as Glottolog or Ethnologue to improve
                    discoverability and to enhance browsing and search
                    experience. The repository may also translate the
                    name into other languages if no language name is
                    given for a particular interface language.
                :ivar object_language_name: The ObjectLanguageName
                    element contains the name of the object language in
                    the version as provided by services such as
                    Glottolog or Ethnologue.
                :ivar object_language_iso639_3_code: The
                    ObjectLanguageISO639-3 element contains an ISO 639-3
                    language code for the object language.
                :ivar object_language_glottolog_code: The
                    ObjectLanguageGlottologCode element contains the
                    Glottolog code for the object language as provided
                    by glottolog.org.
                :ivar object_language_alternative_names: The
                    ObjectLanguageAlternativeNames component contains
                    elements with alternative names for the object
                    language as provided by services such as Glottolog
                    or Ethnologue.
                :ivar object_language_taxonomy: The
                    ObjectLanguageTaxonomy component contains elements
                    with the name of the language family and sub-
                    families or sub-groups the object language belongs
                    to. The values are taken from Glottolog and given in
                    the version as provided by this service.
                :ivar base:
                :ivar ref:
                """

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
                    ComplextypeObjectLanguageIso6393Code1611
                ] = field(
                    default=None,
                    metadata={
                        "name": "ObjectLanguageISO639-3Code",
                        "type": "Element",
                        "required": True,
                    },
                )
                object_language_glottolog_code: Optional[
                    ComplextypeObjectLanguageGlottologCode1611
                ] = field(
                    default=None,
                    metadata={
                        "name": "ObjectLanguageGlottologCode",
                        "type": "Element",
                        "required": True,
                    },
                )
                object_language_alternative_names: Optional[
                    "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageAlternativeNames"
                ] = field(
                    default=None,
                    metadata={
                        "name": "ObjectLanguageAlternativeNames",
                        "type": "Element",
                    },
                )
                object_language_taxonomy: Optional[
                    "BlamCollectionRepositoryV11.CollectionGeneralInfo.CollectionObjectLanguages.CollectionObjectLanguage.ObjectLanguageTaxonomy"
                ] = field(
                    default=None,
                    metadata={
                        "name": "ObjectLanguageTaxonomy",
                        "type": "Element",
                    },
                )
                base: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )
                ref: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.clarin.eu/cmd/1",
                    },
                )

                @dataclass
                class ObjectLanguageAlternativeNames:
                    """
                    :ivar object_language_alternative_name: The
                        ObjectLanguageAlternativeName element contains
                        an alternative name of the object language as
                        provided by services such as Glottolog or
                        Ethnologue.
                    :ivar base:
                    :ivar ref:
                    """

                    object_language_alternative_name: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "ObjectLanguageAlternativeName",
                            "type": "Element",
                        },
                    )
                    base: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.clarin.eu/cmd/1",
                        },
                    )

                @dataclass
                class ObjectLanguageTaxonomy:
                    """
                    :ivar object_language_language_family: The
                        ObjectLanguageLanguageFamily element contains
                        the name of the language family and sub-families
                        or sub-groups the object language belongs to.
                        The values are taken from Glottolog and given in
                        the version as provided by this service.
                    :ivar base:
                    :ivar ref:
                    """

                    object_language_language_family: list[str] = field(
                        default_factory=list,
                        metadata={
                            "name": "ObjectLanguageLanguageFamily",
                            "type": "Element",
                            "min_occurs": 1,
                        },
                    )
                    base: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.clarin.eu/cmd/1",
                        },
                    )

        @dataclass
        class CollectionLocation:
            """
            :ivar collection_geo_location: The CollectionGeoLocation
                element contains a geographical coordinates for a
                location point in the form “LATITUDE,LONGITUDE” as
                decimal degrees (e.g. 50.926735,6.930392 or
                -36.427925,150.076214)
            :ivar collection_location_name: The CollectionLocationName
                element contains the name of a location in the version
                recommended by the data producer. Repositories should
                treat the name provided by this element as the primary
                location name when displaying the metadata in relation
                to this particular data set.The repository may use
                alternative names provided by services such as GeoNames
                to improve discoverability and to enhance the browsing
                and search experience.
            :ivar collection_location_facet: The CollectionLocationFacet
                element contains the name of a location provided by
                services such as GeoNames. This name is used to improve
                discoverability and to enhance the browsing and search
                experience. GeoNames field: “name” (or “toponymName”).
            :ivar collection_region_name: The CollectionRegionName
                element optionally contains the name of an
                administrative subdivision such as state, province, or
                any other politically salient unit in the version
                recommended by the data producer. The data producer can
                decided which level of subdivision is relevant and will
                improve discoverability. Repositories should treat the
                name provided by this element as the primary location
                name when displaying the metadata in relation to this
                particular data set (e.g. collection or collection). The
                repository may use alternative names provided by
                services such as GeoNames to improve discoverability and
                to enhance browsing and search experience.
            :ivar collection_region_facet: The CollectionRegionFacet
                element contains the name of an administrative
                subdivision provided by services such as GeoNames to
                improve discoverability and to enhance browsing and
                search experience. GeoNames field: “adminName1”
            :ivar collection_country_name: The CollectionCountryName
                element contains the name of the country to which the
                location belongs in the version recommended by the data
                producer. Repositories should treat the name provided by
                this element as the primary country name when displaying
                the metadata in relation to this particular data set
                (e.g. collection or collection). The repository may use
                alternative names provided by services such as GeoNames
                to improve discoverability and to enhance browsing and
                search experience.
            :ivar collection_country_facet: The CollectionCountryFacet
                element contains the name of the country as provided by
                services such as GeoNames to improve discoverability and
                to enhance browsing and search experience. GeoNames
                field: “countryName”
            :ivar collection_country_code: The CountryCode element
                contains the ISO 3166-1 alpha 2 code of the country of
                the location as provided by services such as GeoNames
                GeoNames field: countryCode
            :ivar base:
            :ivar ref:
            """

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
                ComplextypeCollectionCountryCode711
            ] = field(
                default=None,
                metadata={
                    "name": "CollectionCountryCode",
                    "type": "Element",
                    "required": True,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

    @dataclass
    class CollectionPublicationInfo:
        """
        :ivar collection_publication_year: CollectionPublicationYear
            contains the year of publication in the form YYYY conforming
            to ISO 8601. The default value is the ingest date into the
            repository unless an embargo has been set for the resource.
            In that case, the end year of the embargo is taken as the
            year of publication. For legacy data, the  value of
            CollectionPublicationDate can be set to a point before the
            ingest. The value of this field should be used to generate a
            bibliographical citation reference for the resource.
        :ivar collection_data_provider: CollectionDataProvider contain
            the name of the data providing entity. The default value
            would be the name of the repository or its holding
            institution. The value of this field can be used to generate
            a bibliographical citation reference for the resource.
        :ivar collection_creators: The CollectionCreator component
            contains information about the creator or creators of the
            resource. CollectionCreators are treated as creators of the
            resource and thus similar to authors in respect to
            quotation, references, and metadata display. Other
            individuals involved in the production or processing of the
            resource should be added as CollectionContributors.
        :ivar collection_contributors: The CollectionContributors
            component contains information about contributors to the
            resource. CollectionContributors are not treated as authors
            in respect to quotation, references, and metadata display.
        :ivar base:
        :ivar ref:
        """

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
            "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionCreators"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionCreators",
                "type": "Element",
                "required": True,
            },
        )
        collection_contributors: Optional[
            "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionContributors"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionContributors",
                "type": "Element",
            },
        )
        base: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )
        ref: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.clarin.eu/cmd/1",
            },
        )

        @dataclass
        class CollectionCreators:
            """
            :ivar collection_creator: The CollectionCreator component
                contains information about the creator of the resource.
            :ivar base:
            :ivar ref:
            """

            collection_creator: list[
                "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionCreators.CollectionCreator"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "CollectionCreator",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class CollectionCreator:
                """
                :ivar creator_name_identifier: The CreatorNameIdentifier
                    contains an URI that uniquely identifies the creator
                    according to an established scheme. ORCID and INSI
                    are considered best practices. An email address in
                    the form of an mailto URI is a fallback.
                :ivar creator_affiliation: The CreatorAffiliation
                    contains the organisational or institutional
                    affiliation of the creator as provided by the
                    depositor.
                :ivar creator_name: The CreatorName component contains
                    the name of the creator. The value of this field can
                    be used to generate a bibliographical citation
                    reference for the resource. This usage should guide
                    the formatting.
                :ivar base:
                :ivar ref:
                :ivar order: The Order attribute indicates the order in
                    which the creators should be displayed.
                """

                creator_name_identifier: list[
                    "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorNameIdentifier"
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
                    "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionCreators.CollectionCreator.CreatorName"
                ] = field(
                    default=None,
                    metadata={
                        "name": "CreatorName",
                        "type": "Element",
                        "required": True,
                    },
                )
                base: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )
                ref: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.clarin.eu/cmd/1",
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
                    """
                    :ivar value:
                    :ivar identifier_type: ORCID and ISNI are considered
                        best practices. An email address in the form of
                        an mailto URI is a fallback.
                    """

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
                            "required": True,
                        },
                    )

                @dataclass
                class CreatorName:
                    """
                    :ivar creator_family_name: The CreatorFamilyName
                        element contains the part of the name of the
                        creator that should be treated as the family
                        name when generating a citation for the
                        resource. This usage should guide the decision
                        which part belongs into this field. If the name
                        of a person consist of only one part, it should
                        go here.
                    :ivar creator_given_name: The CreatorGivenName
                        element contains the part of the name of the
                        creator that should be treated as the given name
                        when generating a citation for the resource.
                        This usage should guide the decision.
                    :ivar base:
                    :ivar ref:
                    """

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
                    base: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.clarin.eu/cmd/1",
                        },
                    )

        @dataclass
        class CollectionContributors:
            """
            :ivar collection_contributor: The CollectionContributor
                component contains information about a contributor to
                the resource.
            :ivar base:
            :ivar ref:
            """

            collection_contributor: list[
                "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionContributors.CollectionContributor"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "CollectionContributor",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class CollectionContributor:
                """
                :ivar contributor_name_identifier: The
                    ContributorNameIdentifier contains an URI that
                    uniquely identifies the contributor according to an
                    established scheme. ORCID and INSI are considered
                    best practices. An email address in the form of an
                    mailto URI is a fallback.
                :ivar contributor_affiliation: The
                    ContributorAffiliation contains the organisational
                    or institutional affiliation of the contributor as
                    provided by the depositor.
                :ivar contributor_role: The ContributorRole contains the
                    organisational or institutional affiliation of the
                    contributor as provided by the depositor.
                :ivar contributor_name: The ContributorName component
                    contains the name of the creator. The value of this
                    field may be used to generate a bibliographical
                    citation reference for the resource. This usage
                    should guide the formatting.
                :ivar base:
                :ivar ref:
                """

                contributor_name_identifier: list[
                    "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorNameIdentifier"
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
                    "BlamCollectionRepositoryV11.CollectionPublicationInfo.CollectionContributors.CollectionContributor.ContributorName"
                ] = field(
                    default=None,
                    metadata={
                        "name": "ContributorName",
                        "type": "Element",
                        "required": True,
                    },
                )
                base: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )
                ref: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.clarin.eu/cmd/1",
                    },
                )

                @dataclass
                class ContributorNameIdentifier:
                    """
                    :ivar value:
                    :ivar identifier_type: ORCID and ISNI are considered
                        best practices. An email address in the form of
                        an mailto URI is a fallback.
                    """

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
                            "required": True,
                        },
                    )

                @dataclass
                class ContributorName:
                    """
                    :ivar contributor_family_name: The
                        ContributorFamilyName element contains the part
                        of the name of the creator that should be
                        treated as the family name when generating a
                        citation for the resource. This usage should
                        guide the decision. If the name of a person
                        consist of only one part, it should go here.
                    :ivar contributor_given_name: The CreatorGivenName
                        element contains the part of the name of the
                        contributor that should be treated as the given
                        name when generating a citation for the
                        resource. This usage should guide the decision.
                    :ivar base:
                    :ivar ref:
                    """

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
                    base: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.clarin.eu/cmd/1",
                        },
                    )

    @dataclass
    class ProjectInfo:
        """
        :ivar project: Project contains descriptive information about
            the project relating to collection data.
        :ivar base:
        :ivar ref:
        """

        project: list["BlamCollectionRepositoryV11.ProjectInfo.Project"] = (
            field(
                default_factory=list,
                metadata={
                    "name": "Project",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
        )
        base: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )
        ref: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.clarin.eu/cmd/1",
            },
        )

        @dataclass
        class Project:
            """
            :ivar project_display_name: The ProjectDisplayName element
                provides a human readable name of the project. The
                preferred form is the abbreviation by which the project
                is generally known. The long form is best placed in the
                project description.
            :ivar project_description: The ProjectDescription element
                provides a human readable description of the project
                including full project name. It should contain a
                description of the project’s objective or activity. The
                content of the ProjectDescription element will be used
                as the human readable description in interfaces. Its
                content can be queried by repositories for free-text
                metadata search. Data producers can provide
                ProjectDescription values for multiple interface
                languages.
            :ivar funder_infos: The FunderInfos component contains
                information about the funding organisation or
                organisations associated with this resource.
            :ivar base:
            :ivar ref:
            """

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
                "BlamCollectionRepositoryV11.ProjectInfo.Project.FunderInfos"
            ] = field(
                default=None,
                metadata={
                    "name": "FunderInfos",
                    "type": "Element",
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class FunderInfos:
                """
                :ivar funder_info: The FunderInfo component contains
                    information about the funding organisation
                    associated with this resource.
                :ivar base:
                :ivar ref:
                """

                funder_info: list[
                    "BlamCollectionRepositoryV11.ProjectInfo.Project.FunderInfos.FunderInfo"
                ] = field(
                    default_factory=list,
                    metadata={
                        "name": "FunderInfo",
                        "type": "Element",
                        "min_occurs": 1,
                    },
                )
                base: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.w3.org/XML/1998/namespace",
                    },
                )
                ref: Optional[str] = field(
                    default=None,
                    metadata={
                        "type": "Attribute",
                        "namespace": "http://www.clarin.eu/cmd/1",
                    },
                )

                @dataclass
                class FunderInfo:
                    """
                    :ivar funder_name: The FunderName element provides
                        the name of the funding organisation. The
                        preferred form is the abbreviation by with the
                        funding agency is generally known.
                    :ivar funder_identifier: The FunderIdentifier
                        contains an URI that uniquely identifies the
                        funding body according to an established scheme.
                    :ivar grant_identifier: GrantIdentifier contains an
                        element that uniquely identifies the grant
                        according to an established scheme. Best
                        Practice: funding body specific identifier such
                        as NSF grant number or BMBF Förderkennzeichen.
                    :ivar grant_uri: The GrantURI contains an URI that
                        uniquely identifies the grant and funding body
                        according to an established scheme.
                    :ivar base:
                    :ivar ref:
                    """

                    funder_name: Optional[str] = field(
                        default=None,
                        metadata={
                            "name": "FunderName",
                            "type": "Element",
                            "required": True,
                        },
                    )
                    funder_identifier: Optional[
                        "BlamCollectionRepositoryV11.ProjectInfo.Project.FunderInfos.FunderInfo.FunderIdentifier"
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
                    base: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.w3.org/XML/1998/namespace",
                        },
                    )
                    ref: Optional[str] = field(
                        default=None,
                        metadata={
                            "type": "Attribute",
                            "namespace": "http://www.clarin.eu/cmd/1",
                        },
                    )

                    @dataclass
                    class FunderIdentifier:
                        """
                        :ivar value:
                        :ivar identifier_type: The IdentifierType
                            attribute determines the identifier type
                            used.
                        """

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
                                "required": True,
                            },
                        )

    @dataclass
    class CollectionAdministrativeInfo:
        """
        :ivar collection_is_identical_to: The CollectionIsIdenticalTo
            element contains an URI that uniquely identifies an
            identical resource. This element should only be used if it
            can be ascertained that the identified resource and the
            current resource will remain identical; else
            CollectionIsDerivationOf should be used. The
            CollectionIsIdenticalTo relationship is based on the
            `hasEquivalent` relationship of the Fedora Relationship
            Ontology (http://www.fedora.info/definitions/1/0/fedora-
            relsext-ontology.rdfs).
        :ivar collection_is_derivation_of: The CollectionIsDerivationOf
            element contains an URI that uniquely identifies the
            resource from which the current resource is derived. The
            CollectionIsDerivationOf relationship is based on the
            `isDerivationOf` relationship of the Fedora Relationship
            Ontology (http://www.fedora.info/definitions/1/0/fedora-
            relsext-ontology.rdfs).
        :ivar access: This element specifies the terms of availability
            of the resource in plain words. The  technical
            implementation of these terms depends on the repository.
        :ivar availability_date: The AvailabilityDate element contains
            the date at which the bundle became or will become
            available. The date must be provided conforming to ISO 8601
            in the form YYYY-MM-DD.
        :ivar license: The License component contains information about
            the license under which the resource is available.
        :ivar rights_holder: The RightsHolder component contains
            information about the individual or institution owning or
            managing the rights in regard to the resource.
        :ivar base:
        :ivar ref:
        """

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
            "BlamCollectionRepositoryV11.CollectionAdministrativeInfo.License"
        ] = field(
            default_factory=list,
            metadata={
                "name": "License",
                "type": "Element",
                "min_occurs": 1,
            },
        )
        rights_holder: list[
            "BlamCollectionRepositoryV11.CollectionAdministrativeInfo.RightsHolder"
        ] = field(
            default_factory=list,
            metadata={
                "name": "RightsHolder",
                "type": "Element",
                "min_occurs": 1,
            },
        )
        base: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )
        ref: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.clarin.eu/cmd/1",
            },
        )

        @dataclass
        class License:
            """
            :ivar license_name: The LicenseName element should provide
                the complete human readable name of a license and
                include version information if applicable.
            :ivar license_identifier: The LicenseIdentifier provides a
                URI for the license.
            :ivar base:
            :ivar ref:
            """

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
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

        @dataclass
        class RightsHolder:
            """
            :ivar rights_holder_name: The RightsHolderName contains the
                name of the individual or institution owning or managing
                the rights over the resource.
            :ivar rights_holder_identifier: The RightsHolderIdentifier
                contains a URI that uniquely identifies the rights
                holder. In the case of an individual, this should be
                achieved by using an established scheme. Best Practice:
                ORCID, ISNI If an individual cannot be referenced by an
                identifier an email address should be given (in the form
                of a mailto URI).
            :ivar base:
            :ivar ref:
            """

            rights_holder_name: Optional[str] = field(
                default=None,
                metadata={
                    "name": "RightsHolderName",
                    "type": "Element",
                    "required": True,
                },
            )
            rights_holder_identifier: list[
                "BlamCollectionRepositoryV11.CollectionAdministrativeInfo.RightsHolder.RightsHolderIdentifier"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "RightsHolderIdentifier",
                    "type": "Element",
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class RightsHolderIdentifier:
                """
                :ivar value:
                :ivar identifier_type: ORCID and ISNI are considered
                    best practices. An email address in the form of a
                    mailto URI is the recommended fallback.
                """

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
                        "required": True,
                    },
                )

    @dataclass
    class CollectionStructuralInfo:
        """
        :ivar collection_additional_metadata_file: The
            CollectionAdditionalMetadataFile component contains metadata
            about additional metadata files contained in the collection.
        :ivar collection_members: The CollectionMembers component
            contains elements referencing the bundles of the collection.
        :ivar base:
        :ivar ref:
        """

        collection_additional_metadata_file: list[
            "BlamCollectionRepositoryV11.CollectionStructuralInfo.CollectionAdditionalMetadataFile"
        ] = field(
            default_factory=list,
            metadata={
                "name": "CollectionAdditionalMetadataFile",
                "type": "Element",
            },
        )
        collection_members: Optional[
            "BlamCollectionRepositoryV11.CollectionStructuralInfo.CollectionMembers"
        ] = field(
            default=None,
            metadata={
                "name": "CollectionMembers",
                "type": "Element",
                "required": True,
            },
        )
        base: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.w3.org/XML/1998/namespace",
            },
        )
        ref: Optional[str] = field(
            default=None,
            metadata={
                "type": "Attribute",
                "namespace": "http://www.clarin.eu/cmd/1",
            },
        )

        @dataclass
        class CollectionAdditionalMetadataFile:
            """
            :ivar file_name: The FileName element contains the name of
                the file as provided by the depositor.
            :ivar file_pid: The FileID element contains a PID that
                uniquely identifies the file described by this
                component.
            :ivar mime_type: Specification of the mime-type of the
                resource.
            :ivar is_metadata_for: The IsMetadataFor element contains a
                PID that uniquely identifies the file described by the
                file described in this component. The IsMetadataFor
                relationship is based on the `isMetadataFor`
                relationship of the Fedora Relationship Ontology
                (http://www.fedora.info/definitions/1/0/fedora-relsext-
                ontology.rdfs).
            :ivar file_description: The FileDescription contains a human
                readable, file specific description. This element should
                be used to provide file specific that cannot be added to
                the collection description. Any information applicable
                to the whole collection should be added to the
                CollectionDescription element.
            :ivar base:
            :ivar ref:
            """

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
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

        @dataclass
        class CollectionMembers:
            """
            :ivar collection_has_collection_member: The
                CollectionHasCollectionMember element contains
                references to a bundle contained in the collection. The
                CollectionHasCollectionMember relationship is based on
                the `hasCollectionMember` relationship of the Fedora
                Relationship Ontology
                (http://www.fedora.info/definitions/1/0/fedora-relsext-
                ontology.rdfs).
            :ivar base:
            :ivar ref:
            """

            collection_has_collection_member: list[
                "BlamCollectionRepositoryV11.CollectionStructuralInfo.CollectionMembers.CollectionHasCollectionMember"
            ] = field(
                default_factory=list,
                metadata={
                    "name": "CollectionHasCollectionMember",
                    "type": "Element",
                    "min_occurs": 1,
                },
            )
            base: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.w3.org/XML/1998/namespace",
                },
            )
            ref: Optional[str] = field(
                default=None,
                metadata={
                    "type": "Attribute",
                    "namespace": "http://www.clarin.eu/cmd/1",
                },
            )

            @dataclass
            class CollectionHasCollectionMember:
                """
                :ivar value:
                :ivar identifier_type: The IdentifierType attribute
                    determines the identifier type used.
                """

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
                        "required": True,
                    },
                )
