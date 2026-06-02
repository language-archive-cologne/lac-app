"""Tests for OAI-PMH BLAM metadata format."""

import pytest
from datetime import date
from django.urls import reverse

from lacos.oaipmh.formats.blam import BLAMSerializer
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_general_info import (
    CollectionGeneralInfo,
    CollectionLocation,
    CollectionObjectLanguage,
)
from lacos.blam.models.collection.collection_publication_info import (
    CollectionPublicationInfo,
    CollectionCreator,
)
from lacos.blam.models.collection.collection_administrative_info import (
    CollectionAdministrativeInfo,
    CollectionLicense,
    CollectionRightsHolder,
)


@pytest.fixture
def sample_collection(db):
    """Create a sample collection with all related models for testing."""
    # Create collection
    collection = Collection.objects.create(
        identifier="hdl:test/blam-oai-001",
        source_version="1.0",
    )

    # Create header
    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Test Creator",
        md_creation_date=date(2024, 1, 15),
        md_self_link="hdl:test/blam-oai-001",
        md_profile="clarin.eu:cr1:p_test",
        md_collection_display_name="BLAM OAI Test",
    )

    # Create location
    location = CollectionLocation.objects.create(
        country_name="Germany",
        country_facet="Germany",
        country_code="DE",
    )

    # Create object language
    obj_lang = CollectionObjectLanguage.objects.create(
        display_name="German",
        name="German",
        iso_639_3_code="deu",
        glottolog_code="stan1295",
    )

    # Create general info
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="hdl:test/blam-oai-001",
        id_type="HANDLE",
        display_title="BLAM OAI Test Collection",
        description="Testing BLAM format in OAI-PMH.",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(obj_lang)

    # Create creator
    creator = CollectionCreator.objects.create(
        family_name="Müller",
        given_name="Hans",
    )

    # Create publication info
    pub_info = CollectionPublicationInfo.objects.create(
        collection=collection,
        publication_year=2024,
        data_provider="Test Provider",
    )
    pub_info.creators.add(creator)

    # Create license
    license_obj = CollectionLicense.objects.create(
        license_name="CC-BY-4.0",
        license_identifier="https://creativecommons.org/licenses/by/4.0/",
        access="open",
    )

    # Create rights holder
    rights_holder = CollectionRightsHolder.objects.create(
        rights_holder_name="Test Institution",
    )

    # Create administrative info
    admin_info = CollectionAdministrativeInfo.objects.create(
        collection=collection,
        access_level="public",
        availability_date=date(2024, 1, 15),
    )
    admin_info.licenses.add(license_obj)
    admin_info.rights_holders.add(rights_holder)

    return collection


@pytest.mark.django_db
def test_blam_format_in_list_metadata_formats(client):
    """Test that BLAM appears in ListMetadataFormats response."""
    response = client.get(reverse("oaipmh:endpoint"), {"verb": "ListMetadataFormats"})
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "blam" in body
    assert "clarin.eu" in body


@pytest.mark.django_db
def test_blam_serializer_with_valid_collection(sample_collection):
    """Test BLAM serializer produces valid XML for a collection."""
    serializer = BLAMSerializer()

    record = {"CollectionID": sample_collection.identifier}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert isinstance(xml_str, str)
    assert "<CMD" in xml_str
    assert 'xmlns="http://www.clarin.eu/cmd/"' in xml_str


@pytest.mark.django_db
def test_blam_serializer_with_missing_collection():
    """Test BLAM serializer handles missing collection gracefully."""
    serializer = BLAMSerializer()

    record = {"CollectionID": "nonexistent-collection-id"}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert "<CMD" in xml_str


@pytest.mark.django_db
def test_blam_serializer_with_empty_record():
    """Test BLAM serializer handles empty record gracefully."""
    serializer = BLAMSerializer()

    record = {}
    xml_str = serializer.serialize(record)

    assert xml_str is not None
    assert "<CMD" in xml_str


@pytest.mark.django_db
def test_list_records_with_blam_format(client, sample_collection):
    """Test ListRecords with BLAM metadataPrefix returns collection."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "blam"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")

    # Should contain BLAM XML structure
    assert "CMD" in body or "record" in body


@pytest.mark.django_db
def test_get_record_with_blam_format(client, sample_collection):
    """Test GetRecord with BLAM metadataPrefix returns one collection."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {
            "verb": "GetRecord",
            "metadataPrefix": "blam",
            "identifier": f"oai:lacos:{sample_collection.identifier}",
        },
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "<GetRecord>" in body
    assert f"<identifier>oai:lacos:{sample_collection.identifier}</identifier>" in body
    assert "CMD" in body


@pytest.mark.django_db
def test_unsupported_metadata_prefix_error(client):
    """Test that unsupported prefix returns proper error."""
    response = client.get(
        reverse("oaipmh:endpoint"),
        {"verb": "ListRecords", "metadataPrefix": "unsupported_format"},
    )
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "cannotDisseminateFormat" in body
