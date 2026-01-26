"""JSON-LD serializer for BLAM Collection metadata.

This serializer outputs JSON-LD that closely mirrors the BLAM XML schema structure,
using BLAM vocabulary terms rather than mapping to external vocabularies like Schema.org.
"""

import json
from typing import Any, Optional

from lacos.blam.models.collection.collection_repository import Collection


# BLAM JSON-LD context - defines the BLAM vocabulary
BLAM_CONTEXT = {
    "@vocab": "http://www.clarin.eu/cmd/1/profiles/clarin.eu:cr1:p_1475136016208/",
    "cmd": "http://www.clarin.eu/cmd/",
    "blam": "http://www.clarin.eu/cmd/1/profiles/clarin.eu:cr1:p_1475136016208/",
    "dcterms": "http://purl.org/dc/terms/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    # Type coercions
    "MdCreationDate": {"@type": "xsd:date"},
    "AvailabilityDate": {"@type": "xsd:date"},
    "RecordingDate": {"@type": "xsd:date"},
    "PublicationYear": {"@type": "xsd:gYear"},
}


class CollectionJsonLdSerializer:
    """Serialize a BLAM Collection to JSON-LD format."""

    def __init__(self, collection: Collection):
        self.collection = collection

    def serialize(self) -> dict[str, Any]:
        """Serialize the collection to a JSON-LD dictionary."""
        data = {
            "@context": BLAM_CONTEXT,
            "@type": "BLAMCollectionRepository",
            "@id": self._get_collection_id(),
        }

        # Header
        header = self.collection.header.first()
        if header:
            data["Header"] = self._serialize_header(header)

        # General Info
        general_info = self.collection.general_info.first()
        if general_info:
            data["CollectionGeneralInfo"] = self._serialize_general_info(general_info)

        # Publication Info
        pub_info = self.collection.publication_info.first()
        if pub_info:
            data["CollectionPublicationInfo"] = self._serialize_publication_info(pub_info)

        # Administrative Info
        admin_info = self.collection.administrative_info.first()
        if admin_info:
            data["CollectionAdministrativeInfo"] = self._serialize_administrative_info(admin_info)

        # Structural Info
        structural_info = self.collection.structural_info.first()
        if structural_info:
            data["CollectionStructuralInfo"] = self._serialize_structural_info(structural_info)

        # Project Info
        if self.collection.project_infos.exists():
            data["ProjectInfo"] = [
                self._serialize_project_info(p) for p in self.collection.project_infos.all()
            ]

        return data

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.serialize(), indent=indent, ensure_ascii=False)

    def _get_collection_id(self) -> str:
        """Get the primary identifier for the collection."""
        general_info = self.collection.general_info.first()
        if general_info and general_info.id_value:
            return general_info.id_value
        return str(self.collection.id)

    def _serialize_header(self, header) -> dict[str, Any]:
        """Serialize the metadata header."""
        data = {}

        if header.md_creator:
            data["MdCreator"] = header.md_creator

        if header.md_creation_date:
            data["MdCreationDate"] = header.md_creation_date.isoformat()

        if header.md_self_link:
            data["MdSelfLink"] = header.md_self_link

        if header.md_profile:
            data["MdProfile"] = header.md_profile

        if header.md_collection_display_name:
            data["MdCollectionDisplayName"] = header.md_collection_display_name

        return data

    def _serialize_general_info(self, info) -> dict[str, Any]:
        """Serialize collection general info."""
        data = {}

        # Collection ID
        if info.id_value:
            data["CollectionId"] = {
                "@value": info.id_value,
                "IdentifierType": info.id_type,
            }

        if info.display_title:
            data["CollectionDisplayTitle"] = info.display_title

        if info.description:
            data["CollectionDescription"] = info.description

        if info.version:
            data["CollectionVersion"] = info.version

        if info.recording_date:
            data["RecordingDate"] = info.recording_date.isoformat()

        # Keywords
        keywords = list(info.keywords.values_list("value", flat=True))
        if keywords:
            data["CollectionKeywords"] = {"CollectionKeyword": keywords}

        # Object Languages
        languages = info.object_languages.all()
        if languages:
            data["CollectionObjectLanguages"] = {
                "CollectionObjectLanguage": [
                    self._serialize_object_language(lang) for lang in languages
                ]
            }

        # Location
        if info.location:
            data["CollectionLocation"] = self._serialize_location(info.location)

        return data

    def _serialize_object_language(self, lang) -> dict[str, Any]:
        """Serialize an object language."""
        data = {}

        if lang.display_name:
            data["ObjectLanguageDisplayName"] = lang.display_name

        if lang.name:
            data["ObjectLanguageName"] = lang.name

        if lang.iso_639_3_code:
            data["ObjectLanguageISO639-3Code"] = lang.iso_639_3_code

        if lang.glottolog_code:
            data["ObjectLanguageGlottologCode"] = lang.glottolog_code

        # Alternative names
        alt_names = list(lang.alternative_names.values_list("value", flat=True))
        if alt_names:
            data["ObjectLanguageAlternativeNames"] = {
                "ObjectLanguageAlternativeName": alt_names
            }

        # Taxonomy / Language families
        try:
            taxonomy = lang.taxonomy
            families = list(taxonomy.language_family.values_list("value", flat=True))
            if families:
                data["ObjectLanguageTaxonomy"] = {
                    "ObjectLanguageLanguageFamily": families
                }
        except Exception:
            pass

        return data

    def _serialize_location(self, location) -> dict[str, Any]:
        """Serialize a location."""
        data = {}

        if location.geo_location:
            data["CollectionGeoLocation"] = location.geo_location

        if location.location_name:
            data["CollectionLocationName"] = location.location_name

        if location.location_facet:
            data["CollectionLocationFacet"] = location.location_facet

        if location.region_name:
            data["CollectionRegionName"] = location.region_name

        if location.region_facet:
            data["CollectionRegionFacet"] = location.region_facet

        if location.country_name:
            data["CollectionCountryName"] = location.country_name

        if location.country_facet:
            data["CollectionCountryFacet"] = location.country_facet

        if location.country_code:
            data["CollectionCountryCode"] = location.country_code

        return data

    def _serialize_publication_info(self, info) -> dict[str, Any]:
        """Serialize collection publication info."""
        data = {}

        if info.publication_year:
            data["PublicationYear"] = info.publication_year

        if info.data_provider:
            data["DataProvider"] = info.data_provider

        # Creators
        creators = info.creators.all()
        if creators:
            data["Creators"] = {
                "Creator": [self._serialize_creator(c) for c in creators]
            }

        # Contributors
        contributors = info.contributors.all()
        if contributors:
            data["Contributors"] = {
                "Contributor": [self._serialize_contributor(c) for c in contributors]
            }

        return data

    def _serialize_creator(self, creator) -> dict[str, Any]:
        """Serialize a creator."""
        data = {}

        if creator.family_name:
            data["CreatorFamilyName"] = creator.family_name

        if creator.given_name:
            data["CreatorGivenName"] = creator.given_name

        if creator.name_identifier:
            data["CreatorNameIdentifier"] = {
                "@value": creator.name_identifier,
                "IdentifierType": creator.name_identifier_type,
            }

        if creator.affiliation:
            data["CreatorAffiliation"] = creator.affiliation

        return data

    def _serialize_contributor(self, contributor) -> dict[str, Any]:
        """Serialize a contributor."""
        data = self._serialize_creator(contributor)  # Same fields as creator

        if contributor.role:
            data["ContributorRole"] = contributor.role

        # Rename keys from Creator* to Contributor*
        renamed = {}
        for key, value in data.items():
            if key.startswith("Creator"):
                renamed[key.replace("Creator", "Contributor")] = value
            else:
                renamed[key] = value

        return renamed

    def _serialize_administrative_info(self, info) -> dict[str, Any]:
        """Serialize collection administrative info."""
        data = {}

        if info.access_level:
            data["AccessLevel"] = info.access_level

        if info.availability_date:
            data["AvailabilityDate"] = info.availability_date

        if info.is_derivation_of:
            data["IsDerivationOf"] = info.is_derivation_of

        # Licenses
        licenses = info.licenses.all()
        if licenses:
            data["Licenses"] = {
                "License": [self._serialize_license(lic) for lic in licenses]
            }

        # Rights Holders
        rights_holders = info.rights_holders.all()
        if rights_holders:
            data["RightsHolders"] = {
                "RightsHolder": [
                    self._serialize_rights_holder(rh) for rh in rights_holders
                ]
            }

        # Identical resources
        identical = info.is_identical_to.all()
        if identical:
            data["IsIdenticalTo"] = [r.uri for r in identical]

        return data

    def _serialize_license(self, license) -> dict[str, Any]:
        """Serialize a license."""
        data = {}

        if license.license_name:
            data["LicenseName"] = license.license_name

        if license.license_identifier:
            data["LicenseIdentifier"] = license.license_identifier

        if license.access:
            data["Access"] = license.access

        return data

    def _serialize_rights_holder(self, rh) -> dict[str, Any]:
        """Serialize a rights holder."""
        data = {}

        if rh.rights_holder_name:
            data["RightsHolderName"] = rh.rights_holder_name

        identifiers = rh.rights_holder_identifiers.all()
        if identifiers:
            data["RightsHolderIdentifiers"] = {
                "RightsHolderIdentifier": [
                    {
                        "@value": ident.identifier,
                        "IdentifierType": ident.identifier_type,
                    }
                    for ident in identifiers
                ]
            }

        return data

    def _serialize_structural_info(self, info) -> dict[str, Any]:
        """Serialize collection structural info."""
        data = {}

        # Additional metadata files
        metadata_files = info.additional_metadata_files.all()
        if metadata_files:
            data["AdditionalMetadataFiles"] = {
                "AdditionalMetadataFile": [
                    self._serialize_additional_metadata_file(f) for f in metadata_files
                ]
            }

        return data

    def _serialize_additional_metadata_file(self, file) -> dict[str, Any]:
        """Serialize an additional metadata file."""
        data = {}

        if file.file_name:
            data["FileName"] = file.file_name

        if file.file_pid:
            data["FilePID"] = file.file_pid

        if file.mime_type:
            data["MimeType"] = file.mime_type

        if file.is_metadata_for:
            data["IsMetadataFor"] = file.is_metadata_for

        if file.file_description:
            data["FileDescription"] = file.file_description

        return data

    def _serialize_project_info(self, project) -> dict[str, Any]:
        """Serialize project info."""
        data = {}

        if project.project_display_name:
            data["ProjectDisplayName"] = project.project_display_name

        if project.project_description:
            data["ProjectDescription"] = project.project_description

        # Funder info
        funders = project.funder_infos.all()
        if funders:
            data["FunderInfos"] = {
                "FunderInfo": [self._serialize_funder_info(f) for f in funders]
            }

        return data

    def _serialize_funder_info(self, funder) -> dict[str, Any]:
        """Serialize funder info."""
        data = {}

        if funder.funder_name:
            data["FunderName"] = funder.funder_name

        if funder.grant_identifier:
            data["GrantIdentifier"] = funder.grant_identifier

        if funder.grant_uri:
            data["GrantURI"] = funder.grant_uri

        identifiers = funder.funder_identifiers.all()
        if identifiers:
            data["FunderIdentifiers"] = {
                "FunderIdentifier": [
                    {
                        "@value": ident.value,
                        "IdentifierType": ident.identifier_type,
                    }
                    for ident in identifiers
                ]
            }

        return data
