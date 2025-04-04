import pytest
import os
from django.core.exceptions import ValidationError
from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.models.collection.collection_repository import Collection
from lacos.blam.models.collection.collection_structural_info import CollectionStructuralInfo
import datetime
from datetime import date


@pytest.fixture
def algerien_xml_content():
    """Load the algerien.xml file content"""
    xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Try alternative paths
        alternate_paths = [
            os.path.join('data', 'algerien', 'v1', 'content', 'algerien.xml'),
            os.path.join('data', 'formatted', 'algerien.xml')
        ]
        for path in alternate_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"Could not find collection XML file at {xml_path} or alternate locations")


@pytest.fixture
def invalid_xml_content():
    """Fixture providing an invalid XML content"""
    return """
    <?xml version="1.0" encoding="UTF-8"?>
    <cmd:CMD xmlns:cmd="http://www.clarin.eu/cmd/1">
        <cmd:Header>
            <cmd:MdCreator>Test Creator</cmd:MdCreator>
        </cmd:Header>
        <cmd:Resources>
            <cmd:ResourceProxyList>
                <cmd:ResourceProxy id="rp1">
                    <cmd:ResourceType>Collection</cmd:ResourceType>
                </cmd:ResourceProxy>
            </cmd:ResourceProxyList>
        </cmd:Resources>
        <cmd:Components>
            <blam:blam-collection-repository-v1_0>
                <blam:collection_general_info>
                    <blam:title>Test Collection</blam:title>
                </blam:collection_general_info>
            </blam:blam-collection-repository-v1_0>
        </cmd:Components>
    </cmd:CMD>
    """


def test_validate_xml_valid_content(algerien_xml_content):
    """Test XML validation with real algerien.xml content"""
    cmd_data = CollectionImporter.validate_xml(algerien_xml_content)
    assert cmd_data is not None
    assert cmd_data.header.md_creation_date.value.year == 2022
    assert cmd_data.header.md_creation_date.value.month == 10
    assert cmd_data.header.md_creation_date.value.day == 26
    assert cmd_data.header.md_self_link.value == "hdl:11341/0000-0000-0000-3D7C"
    assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"


def test_validate_xml_invalid_content(invalid_xml_content):
    """Test XML validation with invalid content"""
    with pytest.raises(ValidationError) as exc_info:
        CollectionImporter.validate_xml(invalid_xml_content)
    assert "Invalid BLAM collection XML" in str(exc_info.value)


@pytest.mark.django_db
def test_import_from_xml_valid_content(algerien_xml_content):
    """Test importing collection from real algerien.xml content"""
    # Import the data
    collection = CollectionImporter.import_from_xml(algerien_xml_content)
    
    # Verify collection was created with correct data
    assert isinstance(collection, Collection)
    
    # Collection.general_info is now a RelatedManager, get the first item
    general_info = collection.general_info.first()
    assert general_info is not None
    assert general_info.display_title == "Interviews about Rock Art"
    
    # Base header is now accessed through a RelatedManager
    base_header = collection.header.first()  # assuming header is the related_name
    assert base_header is not None
    assert base_header.md_self_link == "hdl:11341/0000-0000-0000-3D7C"
    
    # Verify structural info was created (also a RelatedManager)
    structural_info = collection.structural_info.first()
    assert structural_info is not None
    assert isinstance(structural_info, CollectionStructuralInfo)
    
    # In the updated architecture, we don't check members directly on the collection
    # Instead, bundles reference collections, and this would be part of a separate test
    # that verifies bundles are properly linked to this collection
    
    # Verify publication info (RelatedManager)
    publication_info = collection.publication_info.first()
    assert publication_info is not None
    assert publication_info.publication_year == 2022
    assert publication_info.data_provider == "FAIR.rdm im SPP2143 \"Entangled Africa\""
    
    # Verify administrative info (RelatedManager)
    administrative_info = collection.administrative_info.first()
    assert administrative_info is not None
    assert administrative_info.access_level == "public"
    
    # Check that the availability date is correct (it's a date object, not a string)
    expected_date = date(2022, 10, 26)
    assert administrative_info.availability_date == expected_date


@pytest.mark.django_db
def test_import_from_xml_invalid_content(invalid_xml_content):
    """Test importing collection from invalid XML content"""
    with pytest.raises(ValidationError) as exc_info:
        CollectionImporter.import_from_xml(invalid_xml_content)
    assert "Invalid BLAM collection XML" in str(exc_info.value)


@pytest.mark.django_db
def test_import_from_xml_transaction_rollback(algerien_xml_content):
    """Test that transaction is rolled back on error"""
    # Modify the XML to cause an error during import
    invalid_xml = algerien_xml_content.replace("Interviews about Rock Art", "x" * 256)  # Title too long
    
    with pytest.raises(Exception):
        CollectionImporter.import_from_xml(invalid_xml)
    
    # Verify no collection was created
    assert Collection.objects.count() == 0
    assert CollectionStructuralInfo.objects.count() == 0 