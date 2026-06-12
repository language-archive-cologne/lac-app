"""Tests for the Schema.org Dataset JSON-LD on bundle pages (issue #152 follow-up)."""

import json
from datetime import date
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.urls import reverse

from lacos.blam.models.base_indentifiers import (
    AccessTypeChoices,
    IdentifierTypeChoices,
    PersonIdentifierTypeChoices,
)
from lacos.blam.models.bundle.bundle_administrative_info import (
    BundleAdministrativeInfo,
    BundleLicense,
)
from lacos.blam.models.bundle.bundle_general_info import (
    BundleGeneralInfo,
    BundleKeyword,
    BundleLocation,
    BundleObjectLanguage,
    BundleObjectLanguageLanguageFamily,
    BundleObjectLanguageTaxonomy,
)
from lacos.blam.models.bundle.bundle_publication_info import (
    BundleCreator,
    BundlePublicationInfo,
    BundlePublicationInfoCreator,
)
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_structural_info import BundleStructuralInfo
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
)
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
)
from lacos.explorer.bundle_structured_data import build_bundle_json_ld

PUBLIC_BASE_URL = "https://lac.uni-koeln.de"


class _JsonLdScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in = False
        self.scripts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._in = dict(attrs).get("type") == "application/ld+json"
            if self._in:
                self.scripts.append("")

    def handle_data(self, data):
        if self._in:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self._in = False


def _json_ld_scripts(body: str) -> list[str]:
    parser = _JsonLdScriptParser()
    parser.feed(body)
    return parser.scripts


def _create_collection(identifier: str = "hdl:11341/parent-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(country_name="Country")
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=f"id-{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Parent Collection",
        description="Parent.",
        version="1",
        location=location,
    )
    CollectionStructuralInfo.objects.create(collection=collection)
    return collection


def _create_bundle(collection, identifier: str = "hdl:11341/test-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        geo_location="52.0, 13.0",
        location_name="Berlin",
        country_name="Germany",
    )
    general_info = BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=f"id-{identifier}",
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="Test Bundle",
        description="A test bundle.",
        version="2",
        location=location,
    )
    general_info.keywords.add(BundleKeyword.objects.create(value="fieldwork"))
    language = BundleObjectLanguage.objects.create(
        display_name="Totoli",
        name="Totoli",
        iso_639_3_code="txe",
        glottolog_code="toto1304",
    )
    taxonomy = BundleObjectLanguageTaxonomy.objects.create(object_language=language)
    taxonomy.language_family.add(
        BundleObjectLanguageLanguageFamily.objects.create(value="Austronesian")
    )
    general_info.object_languages.add(language)

    pub_info = BundlePublicationInfo.objects.create(
        bundle=bundle, publication_year=2021, data_provider="LAC"
    )
    creator = BundleCreator.objects.create(
        family_name="Bracks",
        given_name="Christoph",
        name_identifier="0000-0002-5431-7682",
        name_identifier_type=PersonIdentifierTypeChoices.ORCID,
    )
    BundlePublicationInfoCreator.objects.create(
        bundlepublicationinfo=pub_info, bundlecreator=creator, order=1
    )

    admin_info = BundleAdministrativeInfo.objects.create(
        bundle=bundle,
        access_level="public",
        availability_date=date(2021, 3, 1),
    )
    admin_info.licenses.add(
        BundleLicense.objects.create(
            license_name="CC BY 4.0",
            license_identifier="https://creativecommons.org/licenses/by/4.0/",
            access=AccessTypeChoices.OPEN,
        )
    )

    BundleStructuralInfo.objects.create(bundle=bundle, is_member_of_collection=collection)
    return bundle


def _build(bundle, collection, access_level="public", media_resources=None):
    pub_info = bundle.publication_info.first()
    admin_info = bundle.administrative_info.first()
    return build_bundle_json_ld(
        bundle,
        public_base_url=PUBLIC_BASE_URL,
        access_level=access_level,
        collection=collection,
        publication_info=pub_info,
        media_resources=media_resources or [],
        licenses=list(admin_info.licenses.all()) if admin_info else [],
    )


@pytest.mark.django_db
def test_bundle_dataset_core_and_is_part_of():
    collection = _create_collection()
    bundle = _create_bundle(collection)
    data = _build(bundle, collection)

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "Dataset"
    assert data["@id"] == "https://hdl.handle.net/11341/test-bundle"
    assert data["name"] == "Test Bundle"
    assert data["version"] == "2"
    assert data["inLanguage"] == "txe"
    assert data["about"]["sameAs"] == (
        "https://glottolog.org/resource/languoid/id/toto1304"
    )
    assert "Austronesian" in data["keywords"]
    assert data["datePublished"] == "2021-03-01"
    assert data["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert data["isPartOf"] == {
        "@type": ["Dataset", "Collection"],
        "@id": "https://hdl.handle.net/11341/parent-collection",
        "name": "Parent Collection",
        "url": (
            PUBLIC_BASE_URL
            + reverse(
                "explorer:collection_detail_by_handle",
                kwargs={"handle": "11341/parent-collection"},
            )
        ),
    }
    assert data["spatialCoverage"]["geo"] == {
        "@type": "GeoCoordinates",
        "latitude": 52.0,
        "longitude": 13.0,
    }


@pytest.mark.django_db
def test_bundle_distribution_from_resources():
    collection = _create_collection("hdl:11341/parent-dist")
    bundle = _create_bundle(collection, "hdl:11341/bundle-dist")
    media = [
        SimpleNamespace(
            file_name="recording.wav",
            mime_type="audio/wav",
            file_pid="hdl:11341/bundle-dist-file",
        )
    ]
    data = _build(bundle, collection, media_resources=media)

    assert data["distribution"] == [
        {
            "@type": "DataDownload",
            "name": "recording.wav",
            "contentUrl": "https://hdl.handle.net/11341/bundle-dist-file",
            "encodingFormat": "audio/wav",
        }
    ]


@pytest.mark.django_db
def test_bundle_restricted_has_no_distribution():
    collection = _create_collection("hdl:11341/parent-restricted")
    bundle = _create_bundle(collection, "hdl:11341/bundle-restricted")
    data = _build(bundle, collection, access_level="restricted", media_resources=[])

    assert data["isAccessibleForFree"] is False
    assert data["conditionsOfAccess"]
    assert "distribution" not in data


@pytest.mark.django_db
@override_settings(
    ALLOWED_HOSTS=["lac.uni-koeln.de"],
    PUBLIC_BASE_URL="https://lac.uni-koeln.de",
)
def test_bundle_page_emits_valid_dataset_json_ld(client):
    collection = _create_collection("hdl:11341/parent-render")
    bundle = _create_bundle(collection, "hdl:11341/bundle-render")

    url = reverse(
        "explorer:bundle_detail_by_handle", kwargs={"handle": bundle.handle_path}
    )
    response = client.get(url, HTTP_HOST="lac.uni-koeln.de")

    assert response.status_code == 200
    scripts = _json_ld_scripts(response.content.decode("utf-8"))
    datasets = [json.loads(s) for s in scripts if json.loads(s).get("@type") == "Dataset"]
    assert len(datasets) == 1
    assert datasets[0]["@id"] == "https://hdl.handle.net/11341/bundle-render"
    assert datasets[0]["isPartOf"]["@id"] == (
        "https://hdl.handle.net/11341/parent-render"
    )
    assert "<" not in scripts[0]
