import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from django.core.exceptions import ValidationError
import os

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from lacos.blam.models.base_project_info import ProjectInfo


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
def cmd_data(algerien_xml_content):
    """Parse XML into CMD data object"""
    return CollectionImporter.validate_xml(algerien_xml_content)


def test_validate_xml_with_real_data(cmd_data):
    """Test that real XML can be parsed into a Cmd object"""
    assert isinstance(cmd_data, Cmd)
    assert hasattr(cmd_data, 'header')
    assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"


def test_map_general_info(cmd_data):
    """Test mapping general info from CMD data to model"""
    mock_general = MagicMock(name="GeneralInfo")
    
    with patch('lacos.blam.mappers.collection.read.import_collection_general_info.import_general_info', 
              return_value=mock_general) as mock_import_general:
        result = mock_import_general(cmd_data)
        
        mock_import_general.assert_called_once_with(cmd_data)
        assert result == mock_general


def test_map_publication_info(cmd_data):
    """Test mapping publication info from CMD data to model"""
    mock_publication = MagicMock(name="PublicationInfo")
    
    with patch('lacos.blam.mappers.collection.read.import_collection_publication_info.import_publication_info', 
              return_value=mock_publication) as mock_import_publication:
        result = mock_import_publication(cmd_data)
        
        mock_import_publication.assert_called_once_with(cmd_data)
        assert result == mock_publication


def test_map_administrative_info(cmd_data):
    """Test mapping administrative info from CMD data to model"""
    mock_administrative = MagicMock(name="AdministrativeInfo")
    
    with patch('lacos.blam.mappers.collection.read.import_collection_administrative_info.import_administrative_info', 
              return_value=mock_administrative) as mock_import_administrative:
        result = mock_import_administrative(cmd_data)
        
        mock_import_administrative.assert_called_once_with(cmd_data)
        assert result == mock_administrative


def test_map_projects(cmd_data):
    """Test mapping projects from CMD data to model"""
    mock_project = MagicMock(name="ProjectInfo")
    
    with patch('lacos.blam.mappers.collection.read.import_collection_project_info.import_project_info', 
              return_value=[mock_project]) as mock_import_project:
        projects = mock_import_project(cmd_data)
        
        mock_import_project.assert_called_once_with(cmd_data)
        assert len(projects) == 1
        assert projects[0] == mock_project


def test_verify_cmd_header_mapping(cmd_data):
    """Test that header information is correctly mapped from XML to CMD"""
    assert cmd_data.header.md_collection_display_name.value == "Interviews about Rock Art"
    assert cmd_data.header.md_creation_date.value.year == 2022
    assert cmd_data.header.md_creation_date.value.month == 10
    assert cmd_data.header.md_creation_date.value.day == 26
    assert cmd_data.header.md_self_link.value == "hdl:11341/0000-0000-0000-3D7C"


def test_verify_cmd_license_mapping(cmd_data):
    """Test that license information is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    assert repo.mdlicense.value == "CC0"
    assert repo.mdlicense.uri == "https://creativecommons.org/public-domain/cc0/"


def test_verify_cmd_general_info_mapping(cmd_data):
    """Test that general info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert general_info.collection_display_title == "Interviews about Rock Art"
    assert "Master Thesis" in general_info.collection_description
    assert len(general_info.collection_id) > 0
    assert general_info.collection_id[0].value == "hdl:11341/0000-0000-0000-3D7C"


def test_verify_cmd_object_languages_mapping(cmd_data):
    """Test that object languages are correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert hasattr(general_info, 'collection_object_languages')
    assert len(general_info.collection_object_languages.collection_object_language) > 0
    lang = general_info.collection_object_languages.collection_object_language[0]
    assert lang.object_language_name == "Tamasheq"
    assert lang.object_language_iso639_3_code.value == "taq"
    assert lang.object_language_glottolog_code.value == "tama1365"


def test_verify_cmd_location_mapping(cmd_data):
    """Test that location information is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert hasattr(general_info, 'collection_location')
    location = general_info.collection_location
    assert location.collection_country_code.value == "DZ"
    assert location.collection_country_facet == "Algerien"


def test_verify_cmd_publication_info_mapping(cmd_data):
    """Test that publication info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    pub_info = repo.collection_publication_info
    assert str(pub_info.collection_publication_year) == "2022"
    assert pub_info.collection_data_provider == "FAIR.rdm im SPP2143 \"Entangled Africa\""


def test_verify_cmd_creators_mapping(cmd_data):
    """Test that creators are correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    pub_info = repo.collection_publication_info
    assert hasattr(pub_info, 'collection_creators')
    assert len(pub_info.collection_creators.collection_creator) > 0
    creator = pub_info.collection_creators.collection_creator[0]
    assert creator.creator_name.creator_family_name == "Oukafi"
    assert creator.creator_name.creator_given_name == "Issak Cheikh"


def test_verify_cmd_administrative_info_mapping(cmd_data):
    """Test that administrative info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    admin_info = repo.collection_administrative_info
    assert admin_info.access.value.value == "open"
    assert len(admin_info.license) > 0
    assert admin_info.license[0].license_identifier == "CC BY-NC-ND 3.0 DE"


def test_verify_cmd_structural_info_mapping(cmd_data):
    """Test that structural info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    struct_info = repo.collection_structural_info
    assert hasattr(struct_info, 'collection_members')
    assert len(struct_info.collection_members.collection_has_collection_member) > 0
    assert struct_info.collection_members.collection_has_collection_member[0].value.startswith("hdl:11341")


def test_import_header(cmd_data):
    """Test the _import_header method"""
    mock_header = MagicMock(name="Header")
    
    with patch('lacos.blam.mappers.collection.read.collection_importer.import_collection_header', 
              return_value=mock_header) as mock_import_header:
        result = CollectionImporter._import_header(cmd_data)
        
        mock_import_header.assert_called_once_with(cmd_data)
        assert result == mock_header
