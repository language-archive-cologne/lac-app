import pytest
from unittest.mock import patch, MagicMock

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.mappers.bundle.read.import_bundle_project_info import import_project_info, create_or_update_project
from lacos.blam.models.base_project_info import ProjectInfo, FunderInfo, FunderIdentifier
from lacos.blam.models.base_indentifiers import FunderIdentifierTypeChoices


@pytest.fixture
def real_bundle_xml():
    """Get the XML content from a real bundle file in the data directory."""
    import os
    xml_path = os.path.join('data', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
    
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'zag_eoi_20141009_1', 'v1', 'content', 'zag_eoi_20141009_1.xml')
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()


@pytest.fixture
def real_cmd_data(real_bundle_xml):
    """Parse real bundle XML into CMD data"""
    with patch('django.core.exceptions.ValidationError', Exception):
        return BundleImporter.validate_xml(real_bundle_xml)


@pytest.mark.django_db
def test_cmd_project_data_parsing(real_cmd_data):
    """Test that project data is correctly parsed from XML"""
    # Get the project info from CMD data
    components = real_cmd_data.components
    project_info = components.blam_bundle_repository_v1_0.project_info
    
    # Verify project info exists
    assert project_info is not None
    assert hasattr(project_info, 'project')
    assert len(project_info.project) > 0
    
    # Check project details
    project = project_info.project[0]
    assert project.project_display_name == "Fieldmethods Zaghawa"
    assert project.project_description is not None
    assert "Zaghawa" in project.project_description
    
    # In this specific XML, the project doesn't have funder info
    # Check if funder_infos attribute exists, but it can be None
    assert hasattr(project, 'funder_infos')
    
    # If funder info exists (which it might not in this specific test data)
    if project.funder_infos:
        assert hasattr(project.funder_infos, 'funder_info')
        assert len(project.funder_infos.funder_info) > 0
        
        funder = project.funder_infos.funder_info[0]
        assert funder.funder_name is not None
        
        # Check for funder identifiers if present
        if hasattr(funder, 'funder_identifier') and funder.funder_identifier:
            identifier = funder.funder_identifier[0]
            assert hasattr(identifier, 'value')
            assert identifier.value is not None


@pytest.mark.django_db
def test_project_info_data_mapping(real_cmd_data):
    """Test that project info is mapped correctly from CMD to Django models"""
    # Test import with real data
    projects = import_project_info(real_cmd_data)
    
    # Verify projects were imported
    assert len(projects) > 0
    project = projects[0]
    
    # Verify it's the correct type
    assert isinstance(project, ProjectInfo)
    
    # Verify fields were mapped correctly
    assert project.project_display_name == "Fieldmethods Zaghawa"
    assert "Zaghawa" in project.project_description
    
    # This specific project doesn't have funder info in the XML
    # So we'll just check that the relation exists, but might be empty
    assert hasattr(project, 'funder_infos')


@pytest.mark.django_db
def test_get_or_create_project_behavior(real_cmd_data):
    """Test that importing the same project data twice doesn't create duplicates"""
    # First import
    projects1 = import_project_info(real_cmd_data)
    assert len(projects1) > 0
    project1 = projects1[0]
    
    # Second import with same data should get existing records
    projects2 = import_project_info(real_cmd_data)
    assert len(projects2) > 0
    project2 = projects2[0]
    
    # Should be the same record
    assert project1.pk == project2.pk
    
    # Count should still be the original count
    count = ProjectInfo.objects.count()
    assert count == len(projects1)
    
    # Count of FunderInfo objects
    initial_funder_count = FunderInfo.objects.count()
    
    # Import again
    import_project_info(real_cmd_data)
    
    # Funder count should remain the same
    assert FunderInfo.objects.count() == initial_funder_count


@pytest.mark.django_db
def test_funder_identifier_handling():
    """Test the funder identifier type mapping function"""
    from lacos.blam.mappers.bundle.read.import_bundle_project_info import map_identifier_type
    from blam_schemas.bundle.blam_bundle_repository_v1_0 import FunderIdentifierIdentifierType
    
    # Test with different identifier types
    assert map_identifier_type(FunderIdentifierIdentifierType.CROSSREF_FUNDER) == FunderIdentifierTypeChoices.CROSSREF_FUNDER.value
    assert map_identifier_type(FunderIdentifierIdentifierType.ISNI) == FunderIdentifierTypeChoices.ISNI.value
    assert map_identifier_type(FunderIdentifierIdentifierType.GRID) == FunderIdentifierTypeChoices.GRID.value
    assert map_identifier_type(FunderIdentifierIdentifierType.OTHER) == FunderIdentifierTypeChoices.OTHER.value
    
    # Test with None (should return default)
    assert map_identifier_type(None) == FunderIdentifierTypeChoices.CROSSREF_FUNDER.value


@pytest.mark.django_db
def test_missing_funder_info_handling():
    """Test that the import function handles missing funder info gracefully"""
    # Create a mock project data object with no funder_infos
    mock_project = MagicMock()
    mock_project.project_display_name = "Test Project"
    mock_project.project_description = "Test Description"
    
    # Create mock without funder_infos attribute
    mock_without_attr = MagicMock()
    mock_without_attr.project_display_name = "No Attr Project"
    mock_without_attr.project_description = "No funder_infos attribute"
    # Deliberately not setting funder_infos attribute
    
    # Create mock with None funder_infos
    mock_with_none = MagicMock()
    mock_with_none.project_display_name = "None Project"
    mock_with_none.project_description = "None funder_infos"
    mock_with_none.funder_infos = None
    
    # Test with no funder_infos attribute
    project1 = create_or_update_project(mock_without_attr)
    assert isinstance(project1, ProjectInfo)
    assert project1.project_display_name == "No Attr Project"
    assert project1.funder_infos.count() == 0
    
    # Test with None funder_infos
    project2 = create_or_update_project(mock_with_none)
    assert isinstance(project2, ProjectInfo)
    assert project2.project_display_name == "None Project"
    assert project2.funder_infos.count() == 0
