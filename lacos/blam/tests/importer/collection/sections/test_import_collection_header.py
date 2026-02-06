import pytest
from unittest.mock import patch
from datetime import datetime
from django.utils import timezone

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_header import import_collection_header
from lacos.blam.models.collection.collection_header import CollectionHeader
from lacos.blam.models.collection.collection_repository import Collection


@pytest.fixture
def test_collection():
    """Create a test collection for testing."""
    return Collection.objects.create(identifier="test-collection-header")


@pytest.fixture
def real_collection_xml():
    """Get the XML content from a real collection file in the data directory."""
    import os
    xml_path = os.path.join('data', 'algerien', 'algerien', 'v1', 'content', 'algerien.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
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
def real_cmd_data(real_collection_xml):
    """Parse real collection XML into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return CollectionImporter.validate_xml(real_collection_xml)


@pytest.fixture
def cmd_data():
    """Create sample CMD data for testing"""
    cmd = type('obj', (object,), {})
    cmd.header = type('obj', (object,), {})
    
    # Create header data
    header = cmd.header
    header.md_creator = [type('obj', (object,), {'value': 'Test Creator'})]
    header.md_creation_date = type('obj', (object,), {'value': datetime(2022, 10, 26).date()})
    header.md_self_link = type('obj', (object,), {'value': 'http://example.com/test'})
    header.md_profile = type('obj', (object,), {'value': 'http://example.com/profile'})
    header.md_collection_display_name = type('obj', (object,), {'value': 'Test Collection'})
    
    return cmd


@pytest.mark.django_db
def test_cmd_data_parsing(real_cmd_data):
    """Test that CMD data is correctly parsed from XML"""
    # Get the header from CMD data
    header_data = real_cmd_data.header
    
    # Verify basic fields from algerien.xml
    xml_date = header_data.md_creation_date.value
    expected_date = datetime(2022, 10, 26).date()
    assert xml_date.year == expected_date.year
    assert xml_date.month == expected_date.month
    assert xml_date.day == expected_date.day
    assert header_data.md_self_link.value == "hdl:11341/0000-0000-0000-3D7C"
    assert header_data.md_profile.value == "http://catalog.clarin.eu/ds/ComponentRegistry/rest/registry/1.1/profiles/clarin.eu:cr1:p_1721373444015/xsd"
    assert header_data.md_collection_display_name.value == "Interviews about Rock Art"


@pytest.mark.django_db
def test_header_data_mapping(real_cmd_data, test_collection):
    """Test that header data is mapped correctly from CMD to Django model"""
    # Test import with real data
    header = import_collection_header(real_cmd_data, test_collection)
    
    # Verify the object was created and fields were set correctly
    assert isinstance(header, CollectionHeader)
    assert header.md_creation_date == datetime(2022, 10, 26).date()
    assert header.md_self_link == "hdl:11341/0000-0000-0000-3D7C"
    assert header.md_profile == "http://catalog.clarin.eu/ds/ComponentRegistry/rest/registry/1.1/profiles/clarin.eu:cr1:p_1721373444015/xsd"
    assert header.md_collection_display_name == "Interviews about Rock Art"
    assert header.collection == test_collection


@pytest.mark.django_db
def test_get_or_create_behavior(real_cmd_data, test_collection):
    """Test that importing the same data twice doesn't create duplicates"""
    # First import
    header1 = import_collection_header(real_cmd_data, test_collection)
    
    # Second import with same collection should get existing record
    header2 = import_collection_header(real_cmd_data, test_collection)
    
    # Should be the same record
    assert header1.pk == header2.pk
    
    # Count should still be 1
    count = CollectionHeader.objects.filter(collection=test_collection).count()
    assert count == 1


@pytest.mark.django_db
def test_missing_data_handling(cmd_data, test_collection):
    """Test handling of missing data in header"""
    # Remove some fields to test default values
    del cmd_data.header.md_creator
    del cmd_data.header.md_creation_date
    del cmd_data.header.md_self_link
    del cmd_data.header.md_profile
    del cmd_data.header.md_collection_display_name
    
    # Import should still work with defaults
    header = import_collection_header(cmd_data, test_collection)
    
    # Verify default values
    assert header.md_creator == ""
    assert header.md_creation_date == timezone.now().date()
    assert header.md_self_link == ""
    assert header.md_profile == ""
    assert header.md_collection_display_name is None
    assert header.collection == test_collection


@pytest.mark.django_db
def test_multiple_creators_handling(test_collection):
    """Test handling of multiple creators in header"""
    cmd = type('obj', (object,), {})
    cmd.header = type('obj', (object,), {})
    header = cmd.header
    
    # Set multiple creators
    header.md_creator = [
        type('obj', (object,), {'value': 'Creator 1'}),
        type('obj', (object,), {'value': 'Creator 2'})
    ]
    header.md_self_link = type('obj', (object,), {'value': 'http://example.com/test'})
    
    # Import should use first creator
    header_model = import_collection_header(cmd, test_collection)
    assert header_model.md_creator == "Creator 1"
    assert header_model.collection == test_collection


@pytest.mark.django_db
def test_imports_md_license_from_repository_component(test_collection):
    cmd = type("obj", (object,), {})()
    cmd.header = type("obj", (object,), {})()
    cmd.header.md_creator = [type("obj", (object,), {"value": "Test Creator"})]
    cmd.header.md_creation_date = type("obj", (object,), {"value": datetime(2022, 10, 26).date()})
    cmd.header.md_self_link = type("obj", (object,), {"value": "http://example.com/test-license"})
    cmd.header.md_profile = type("obj", (object,), {"value": "http://example.com/profile"})
    cmd.header.md_collection_display_name = type("obj", (object,), {"value": "Test Collection"})

    cmd.components = type("obj", (object,), {})()
    cmd.components.blam_collection_repository_v1_2 = type("obj", (object,), {})()
    cmd.components.blam_collection_repository_v1_2.mdlicense = type(
        "obj",
        (object,),
        {
            "value": "CC0",
            "uri": "https://creativecommons.org/public-domain/cc0/",
        },
    )

    header = import_collection_header(cmd, test_collection)

    assert header.md_license == "CC0"
    assert header.md_license_uri == "https://creativecommons.org/public-domain/cc0/"
