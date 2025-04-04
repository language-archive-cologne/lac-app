import pytest
from unittest.mock import patch, MagicMock
import os
from django.core.exceptions import ValidationError

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from lacos.blam.mappers.collection.read.import_collection_structural_info import (
    import_structural_info,
    import_additional_metadata_files
)
from lacos.blam.models.collection.collection_structural_info import (
    CollectionStructuralInfo,
    CollectionAdditionalMetadataFile
)
from lacos.blam.models.collection.collection_repository import Collection
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd


@pytest.fixture
def test_collection():
    """Create a test collection for testing"""
    return Collection.objects.create()


@pytest.fixture
def real_collection_xml():
    """Get the XML content from algerien.xml."""
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
        
        raise FileNotFoundError(f"Could not find algerien.xml at {xml_path} or alternate locations")


@pytest.fixture
def real_cmd_data(real_collection_xml):
    """Parse algerien.xml content into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return CollectionImporter.validate_xml(real_collection_xml)


@pytest.mark.django_db
def test_xml_parsing_creates_valid_cmd_data(real_collection_xml):
    """Test that algerien.xml is correctly parsed into CMD data structure."""
    cmd_data = CollectionImporter.validate_xml(real_collection_xml)
    
    # Verify basic CMD structure from algerien.xml
    assert cmd_data is not None
    assert cmd_data.header.md_creation_date.value.year == 2022
    assert cmd_data.header.md_creation_date.value.month == 10
    assert cmd_data.header.md_creation_date.value.day == 26
    assert cmd_data.header.md_self_link.value == "hdl:11341/0000-0000-0000-3D7C"
    assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"
    
    # Verify component structure
    assert hasattr(cmd_data, 'components')
    assert hasattr(cmd_data.components, 'blam_collection_repository_v1_0')


@pytest.mark.django_db
def test_structural_info_section_in_cmd_data(real_cmd_data):
    """Test that the structural info section is correctly parsed from algerien.xml."""
    # Extract structural info section
    assert hasattr(real_cmd_data.components.blam_collection_repository_v1_0, 'collection_structural_info')
    
    structural_info = real_cmd_data.components.blam_collection_repository_v1_0.collection_structural_info
    
    # Verify collection members section exists
    assert hasattr(structural_info, 'collection_members')
    assert hasattr(structural_info.collection_members, 'collection_has_collection_member')
    
    # Count the members - algerien.xml has 26 members
    members = structural_info.collection_members.collection_has_collection_member
    assert len(members) == 26
    
    # Verify some specific member identifiers from algerien.xml
    member_identifiers = [member.value for member in members]
    assert "hdl:11341/0000-0000-0000-3D7E" in member_identifiers
    assert "hdl:11341/0000-0000-0000-3D80" in member_identifiers
    assert "hdl:11341/0000-0000-0000-3D82" in member_identifiers
    assert "hdl:11341/0000-0000-0000-3DBF" in member_identifiers  # Last member


@pytest.mark.django_db
def test_import_structural_info_full_process(real_cmd_data, test_collection):
    """Test the full import_structural_info function with data from algerien.xml."""
    # Call the function we're testing
    structural_info = import_structural_info(real_cmd_data, test_collection)
    
    # Verify the model was created with correct data
    assert isinstance(structural_info, CollectionStructuralInfo)
    assert structural_info.pk is not None
    assert structural_info.collection == test_collection
    
    # Verify no additional metadata files (algerien.xml doesn't have any)
    assert structural_info.additional_metadata_files.count() == 0
    
    # Test that importing again doesn't create a duplicate
    structural_info2 = import_structural_info(real_cmd_data, test_collection)
    assert structural_info.pk == structural_info2.pk
    assert CollectionStructuralInfo.objects.filter(collection=test_collection).count() == 1


@pytest.mark.django_db
def test_import_additional_metadata_files_function(test_collection):
    """
    Test the import_additional_metadata_files function.
    
    Note: algerien.xml doesn't have metadata files, so we create a mock schema.
    """
    # Create a structural info to add metadata files to
    structural_info = CollectionStructuralInfo.objects.create(collection=test_collection)
    
    # Create a mock schema with metadata files (since algerien.xml doesn't have any)
    class MockMetadataFile:
        def __init__(self, name, pid, mime_type, is_metadata_for, description=None):
            self.file_name = name
            self.file_pid = pid
            self.mime_type = mime_type
            self.is_metadata_for = is_metadata_for
            if description:
                self.file_description = description
    
    class MockSchema:
        def __init__(self):
            self.collection_additional_metadata_file = [
                MockMetadataFile(
                    name="test.xml",
                    pid="test:pid:123",
                    mime_type="application/xml",
                    is_metadata_for="collection",
                    description="Test metadata file"
                )
            ]
    
    # Call the function we're testing
    import_additional_metadata_files(structural_info, MockSchema())
    
    # Verify metadata file was created and associated
    assert structural_info.additional_metadata_files.count() == 1
    
    # Verify metadata file details
    metadata_file = structural_info.additional_metadata_files.first()
    assert metadata_file.file_name == "test.xml"
    assert metadata_file.file_pid == "test:pid:123"
    assert metadata_file.mime_type == "application/xml"
    assert metadata_file.is_metadata_for == "collection"
    assert metadata_file.file_description == "Test metadata file"
    
    # Verify collection relationship
    assert structural_info.collection == test_collection 