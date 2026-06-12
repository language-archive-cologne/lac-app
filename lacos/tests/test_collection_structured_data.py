"""Tests for the Schema.org Dataset JSON-LD on collection pages (issue #152)."""

import json
from datetime import date
from html.parser import HTMLParser

import pytest
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.base_indentifiers import (
    AccessTypeChoices,
    IdentifierTypeChoices,
    PersonIdentifierTypeChoices,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionIdenticalResource,
    CollectionLicense,
    CollectionRightsHolder,
    CollectionRightsHolderIdentifier,
)
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionKeyword,
    CollectionLocation,
    CollectionObjectLanguage,
    CollectionObjectLanguageLanguageFamily,
    CollectionObjectLanguageTaxonomy,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionCreator,
    CollectionPublicationInfo,
    CollectionPublicationInfoCreator,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionAdditionalMetadataFile,
    CollectionStructuralInfo,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.explorer.collection_structured_data import build_collection_json_ld

PUBLIC_BASE_URL = "https://lac.uni-koeln.de"


class _JsonLdScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_json_ld = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        self._in_json_ld = dict(attrs).get("type") == "application/ld+json"
        if self._in_json_ld:
            self.scripts.append("")

    def handle_data(self, data):
        if self._in_json_ld:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_json_ld = False


def _json_ld_scripts(body: str) -> list[str]:
    parser = _JsonLdScriptParser()
    parser.feed(body)
    return parser.scripts


def _build_rich_collection(identifier: str = "hdl:11341/test-totoli") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        geo_location="1.038611, 120.817778",
        location_name="Tolitoli",
        region_name="Central Sulawesi",
        country_name="Indonesia",
        country_code="ID",
    )
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"id-{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Totoli Archive Cologne",
        description="A corpus of Totoli language documentation.",
        version="1",
        location=location,
    )
    general_info.keywords.add(CollectionKeyword.objects.create(value="recordings"))

    language = CollectionObjectLanguage.objects.create(
        display_name="Totoli",
        name="Totoli",
        iso_639_3_code="txe",
        glottolog_code="toto1304",
    )
    taxonomy = CollectionObjectLanguageTaxonomy.objects.create(object_language=language)
    taxonomy.language_family.add(
        CollectionObjectLanguageLanguageFamily.objects.create(value="Austronesian")
    )
    general_info.object_languages.add(language)

    pub_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2020,
        data_provider="Language Archive Cologne",
    )
    creator_b = CollectionCreator.objects.create(
        family_name="Bracks",
        given_name="Christoph Alexander",
        name_identifier="0000-0002-5431-7682",
        name_identifier_type=PersonIdentifierTypeChoices.ORCID,
        affiliation="University of Cologne",
    )
    creator_a = CollectionCreator.objects.create(
        family_name="Himmelmann",
        given_name="Nikolaus Philipp",
        name_identifier="0000-0002-4385-8395",
        name_identifier_type=PersonIdentifierTypeChoices.ORCID,
    )
    # Insert out of citation order; explicit order must win.
    CollectionPublicationInfoCreator.objects.create(
        collectionpublicationinfo=pub_info, collectioncreator=creator_a, order=2
    )
    CollectionPublicationInfoCreator.objects.create(
        collectionpublicationinfo=pub_info, collectioncreator=creator_b, order=1
    )

    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date(2020, 5, 27),
        is_derivation_of="https://example.org/source",
    )
    admin_info.licenses.add(
        CollectionLicense.objects.create(
            license_name="CC BY 4.0",
            license_identifier="https://creativecommons.org/licenses/by/4.0/",
            access=AccessTypeChoices.OPEN,
        )
    )
    rights_holder = CollectionRightsHolder.objects.create(
        rights_holder_name="Nikolaus P. Himmelmann",
    )
    rights_holder.rights_holder_identifiers.add(
        CollectionRightsHolderIdentifier.objects.create(
            identifier="0000-0002-4385-8395",
            identifier_type="ORCID",
        )
    )
    admin_info.rights_holders.add(rights_holder)
    admin_info.is_identical_to.add(
        CollectionIdenticalResource.objects.create(uri="https://example.org/identical")
    )

    structural_info = CollectionStructuralInfo.objects.create(collection=collection)
    structural_info.additional_metadata_files.add(
        CollectionAdditionalMetadataFile.objects.create(
            file_name="metadata_totoli.xlsm",
            file_pid="hdl:11341/test-meta",
            mime_type="application/vnd.ms-excel.sheet.macroEnabled.12",
            is_metadata_for=identifier,
            file_description="The metadata Excel file.",
        )
    )

    for index in range(2):
        bundle = Bundle.objects.create(identifier=f"{identifier}-bundle-{index}")
        BundleStructuralInfo.objects.create(
            bundle=bundle, is_member_of_collection=collection
        )

    return collection


def _build(collection, access_level="public"):
    pub_info = collection.get_publication_info
    admin_info = collection.get_administrative_info
    structural_info = collection.structural_info.first()
    return build_collection_json_ld(
        collection,
        public_base_url=PUBLIC_BASE_URL,
        access_level=access_level,
        publication_info=pub_info,
        metadata_files=(
            list(structural_info.additional_metadata_files.all())
            if structural_info
            else []
        ),
        licenses=list(admin_info.licenses.all()) if admin_info else [],
    )


@pytest.mark.django_db
def test_dataset_core_identity_and_typing():
    data = _build(_build_rich_collection())

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == ["Dataset", "Collection"]
    assert data["@id"] == "https://hdl.handle.net/11341/test-totoli"
    assert data["url"] == (
        f"{PUBLIC_BASE_URL}"
        + reverse(
            "explorer:collection_detail_by_handle",
            kwargs={"handle": "11341/test-totoli"},
        )
    )
    assert data["identifier"] == [
        {
            "@type": "PropertyValue",
            "propertyID": "hdl",
            "value": "11341/test-totoli",
            "url": "https://hdl.handle.net/11341/test-totoli",
        }
    ]
    assert data["name"] == "Totoli Archive Cologne"
    assert data["version"] == "1"
    assert "@graph" not in data


@pytest.mark.django_db
def test_dataset_language_keywords_and_spatial():
    data = _build(_build_rich_collection())

    assert data["inLanguage"] == "txe"
    assert data["about"] == {
        "@type": "Language",
        "name": "Totoli",
        "alternateName": "txe",
        "sameAs": "https://glottolog.org/resource/languoid/id/toto1304",
    }
    assert "Austronesian" in data["keywords"]
    assert "recordings" in data["keywords"]
    assert data["spatialCoverage"] == {
        "@type": "Place",
        "name": "Tolitoli, Central Sulawesi, Indonesia",
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": 1.038611,
            "longitude": 120.817778,
        },
    }


@pytest.mark.django_db
def test_dataset_access_rights_and_provenance():
    data = _build(_build_rich_collection())

    assert data["datePublished"] == "2020-05-27"
    assert data["isAccessibleForFree"] is True
    assert "conditionsOfAccess" not in data
    assert data["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert data["isBasedOn"] == "https://example.org/source"
    assert data["sameAs"] == "https://example.org/identical"
    assert data["collectionSize"] == 2


@pytest.mark.django_db
def test_dataset_agents():
    data = _build(_build_rich_collection())

    assert data["copyrightHolder"] == {
        "@type": "Person",
        "@id": "https://orcid.org/0000-0002-4385-8395",
        "name": "Nikolaus P. Himmelmann",
    }
    # creator order follows the explicit @Order, not insertion order.
    assert [c["familyName"] for c in data["creator"]] == ["Bracks", "Himmelmann"]
    assert data["creator"][0] == {
        "@type": "Person",
        "@id": "https://orcid.org/0000-0002-5431-7682",
        "givenName": "Christoph Alexander",
        "familyName": "Bracks",
        "name": "Christoph Alexander Bracks",
        "affiliation": {"@type": "Organization", "name": "University of Cologne"},
    }


@pytest.mark.django_db
def test_dataset_subject_of_and_record_nodes():
    data = _build(_build_rich_collection())

    assert data["subjectOf"] == {
        "@type": "MediaObject",
        "name": "metadata_totoli.xlsm",
        "contentUrl": "https://hdl.handle.net/11341/test-meta",
        "encodingFormat": "application/vnd.ms-excel.sheet.macroEnabled.12",
        "description": "The metadata Excel file.",
    }
    assert data["publisher"]["@id"] == "https://lac.uni-koeln.de/#org"
    assert data["publisher"]["identifier"]["propertyID"] == "re3data"
    assert data["includedInDataCatalog"]["@id"] == "https://lac.uni-koeln.de/#catalog"
    assert data["sdLicense"] == "https://creativecommons.org/publicdomain/zero/1.0/"
    assert data["sdPublisher"] == {
        "@type": "Organization",
        "@id": "https://lac.uni-koeln.de/#org",
        "name": "Language Archive Cologne",
    }


@pytest.mark.django_db
def test_minimal_collection_without_administrative_info():
    collection = Collection.objects.create(identifier="hdl:11341/minimal")
    location = CollectionLocation.objects.create(country_name="Country")
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="id-minimal",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Minimal Collection",
        description="Minimal.",
        version="1",
        location=location,
    )
    pub_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2019,
        data_provider="LAC",
    )

    data = build_collection_json_ld(
        collection,
        public_base_url=PUBLIC_BASE_URL,
        access_level="restricted",
        publication_info=pub_info,
        metadata_files=[],
        licenses=[],
    )

    assert data["datePublished"] == "2019"
    assert data["isAccessibleForFree"] is False
    assert data["conditionsOfAccess"]
    assert "license" not in data
    assert "copyrightHolder" not in data
    assert "isBasedOn" not in data
    assert "subjectOf" not in data
    assert data["collectionSize"] == 0


@pytest.mark.django_db
def test_unparseable_geo_location_is_omitted_not_repaired():
    collection = Collection.objects.create(identifier="hdl:11341/badgeo")
    location = CollectionLocation.objects.create(
        geo_location="not-coordinates", location_name="Somewhere"
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="id-badgeo",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Bad Geo",
        description="x",
        version="1",
        location=location,
    )
    data = build_collection_json_ld(
        collection,
        public_base_url=PUBLIC_BASE_URL,
        access_level="public",
        publication_info=None,
        metadata_files=[],
        licenses=[],
    )

    assert data["spatialCoverage"] == {"@type": "Place", "name": "Somewhere"}


@pytest.mark.django_db
@override_settings(
    ALLOWED_HOSTS=["lac.uni-koeln.de"],
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
)
def test_collection_page_emits_dataset_json_ld(client):
    collection = _build_rich_collection("hdl:11341/test-render")

    url = reverse(
        "explorer:collection_detail_by_handle",
        kwargs={"handle": collection.handle_path},
    )
    response = client.get(url, HTTP_HOST="lac.uni-koeln.de")

    assert response.status_code == 200
    scripts = _json_ld_scripts(response.content.decode("utf-8"))
    datasets = [json.loads(s) for s in scripts if "Dataset" in json.loads(s).get("@type", [])]
    assert len(datasets) == 1
    assert datasets[0]["@id"] == "https://hdl.handle.net/11341/test-render"
    assert "<" not in scripts[0]
