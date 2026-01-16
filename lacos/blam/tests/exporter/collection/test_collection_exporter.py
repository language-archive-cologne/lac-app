"""Tests for collection exporter."""

import pytest
from datetime import date
from xml.etree import ElementTree as ET

from lacos.blam.mappers.collection.write import CollectionExporter
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
        identifier="hdl:test/collection-001",
        source_version="1.0",
    )

    # Create header
    CollectionHeader.objects.create(
        collection=collection,
        md_creator="Test Creator",
        md_creation_date=date(2024, 1, 15),
        md_self_link="hdl:test/collection-001",
        md_profile="clarin.eu:cr1:p_test",
        md_collection_display_name="Test Collection",
    )

    # Create location
    location = CollectionLocation.objects.create(
        country_name="Germany",
        country_facet="Germany",
        country_code="DE",
    )

    # Create object language
    obj_lang = CollectionObjectLanguage.objects.create(
        display_name="English",
        name="English",
        iso_639_3_code="eng",
        glottolog_code="stan1293",
    )

    # Create general info
    general_info = CollectionGeneralInfo.objects.create(
        collection=collection,
        id_value="hdl:test/collection-001",
        id_type="HANDLE",
        display_title="Test Collection Title",
        description="A test collection for unit testing.",
        version="1.0",
        location=location,
    )
    general_info.object_languages.add(obj_lang)

    # Create creator
    creator = CollectionCreator.objects.create(
        family_name="Smith",
        given_name="John",
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
        rights_holder_name="Test University",
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
def test_export_produces_valid_xml(sample_collection):
    """Test that exporter produces valid XML output."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert xml_output is not None
    assert "<CMD" in xml_output
    assert 'xmlns="http://www.clarin.eu/cmd/"' in xml_output


@pytest.mark.django_db
def test_export_contains_header(sample_collection):
    """Test that exported XML contains header information."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "MdCreator" in xml_output
    assert "MdSelfLink" in xml_output
    assert "hdl:test/collection-001" in xml_output


@pytest.mark.django_db
def test_export_contains_general_info(sample_collection):
    """Test that exported XML contains general info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "CollectionDisplayTitle" in xml_output
    assert "Test Collection Title" in xml_output
    assert "CollectionDescription" in xml_output


@pytest.mark.django_db
def test_export_contains_publication_info(sample_collection):
    """Test that exported XML contains publication info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "CollectionPublicationYear" in xml_output
    assert "CollectionDataProvider" in xml_output
    assert "Test Provider" in xml_output


@pytest.mark.django_db
def test_export_contains_administrative_info(sample_collection):
    """Test that exported XML contains administrative info."""
    exporter = CollectionExporter()

    xml_output = exporter.export(sample_collection)

    assert "AvailabilityDate" in xml_output
    assert "License" in xml_output
    assert "RightsHolder" in xml_output


@pytest.mark.django_db
def test_export_to_element_returns_element(sample_collection):
    """Test that export_to_element returns an XML Element."""
    exporter = CollectionExporter()

    element = exporter.export_to_element(sample_collection)

    assert isinstance(element, ET.Element)
    assert "CMD" in element.tag
