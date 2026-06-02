import pytest
from django.urls import reverse

from lacos.blam.models.base_indentifiers import IdentifierTypeChoices
from lacos.blam.models.bundle.bundle_general_info import BundleGeneralInfo, BundleLocation
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.collection.collection_general_info import CollectionGeneralInfo, CollectionLocation
from lacos.blam.models.collection.collection_repository import Collection


def _create_collection(identifier: str = "hdl:test/oai-collection") -> Collection:
    collection = Collection.objects.create(identifier=identifier)
    location = CollectionLocation.objects.create(
        location_name="OAI Collection Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="OAI Test Collection",
        description="Collection metadata for GetRecord tests",
        version="1.0",
        location=location,
    )
    return collection


def _create_bundle(collection: Collection, identifier: str = "hdl:test/oai-bundle") -> Bundle:
    bundle = Bundle.objects.create(identifier=identifier)
    location = BundleLocation.objects.create(
        location_name="OAI Bundle Site",
        region_name="Region",
        country_name="Country",
        country_code="TC",
    )
    BundleGeneralInfo.objects.create(
        bundle=bundle,
        id_value=identifier,
        id_type=IdentifierTypeChoices.HANDLE,
        display_title="OAI Test Bundle",
        description="Bundle metadata for GetRecord tests",
        version="1.0",
        location=location,
    )
    return bundle


@pytest.mark.django_db
def test_identify(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "Identify"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<Identify>" in body
    assert "<repositoryName>" in body
    assert "<adminEmail>lac-helpdesk@uni-koeln.de</adminEmail>" in body
    assert "support@example.com" not in body


@pytest.mark.django_db
def test_list_metadata_formats(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListMetadataFormats"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "oai_dc" in body
    assert "olac" in body
    assert "schema_org" in body


@pytest.mark.django_db
def test_list_sets(client):
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListSets"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "collections" in body
    assert "bundles" in body


@pytest.mark.django_db
def test_list_records_without_data_returns_error(client):
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "oai_dc"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "noRecordsMatch" in body


@pytest.mark.django_db
def test_get_record_returns_collection_record(client):
    collection = _create_collection()

    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "oai_dc",
            "identifier": f"oai:lacos:{collection.identifier}",
        },
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<GetRecord>" in body
    assert f"<identifier>oai:lacos:{collection.identifier}</identifier>" in body
    assert "<dc:title>OAI Test Collection</dc:title>" in body


@pytest.mark.django_db
def test_get_record_returns_bundle_record(client):
    collection = _create_collection()
    bundle = _create_bundle(collection)

    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "oai_dc",
            "identifier": f"oai:lacos:bundle:{bundle.identifier}",
        },
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<GetRecord>" in body
    assert f"<identifier>oai:lacos:bundle:{bundle.identifier}</identifier>" in body
    assert "<dc:title>OAI Test Bundle</dc:title>" in body


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("metadata_prefix", "expected_marker"),
    [
        ("olac", "<olac:olac"),
        ("schema_org", "<schema:Dataset"),
    ],
)
def test_get_record_supports_xml_metadata_formats(
    client,
    metadata_prefix,
    expected_marker,
):
    collection = _create_collection()

    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": metadata_prefix,
            "identifier": f"oai:lacos:{collection.identifier}",
        },
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<GetRecord>" in body
    assert f"<identifier>oai:lacos:{collection.identifier}</identifier>" in body
    assert expected_marker in body


@pytest.mark.django_db
def test_get_record_requires_identifier(client):
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "GetRecord", "metadataPrefix": "oai_dc"},
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "badArgument" in body
    assert "identifier is required" in body


@pytest.mark.django_db
def test_get_record_unknown_identifier_returns_id_does_not_exist(client):
    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "oai_dc",
            "identifier": "oai:lacos:hdl:test/missing",
        },
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "idDoesNotExist" in body


@pytest.mark.django_db
def test_get_record_unsupported_metadata_prefix_returns_error(client):
    collection = _create_collection()

    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "unsupported_format",
            "identifier": f"oai:lacos:{collection.identifier}",
        },
    )

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "cannotDisseminateFormat" in body
