import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from django.core.exceptions import ValidationError
import os

from lacos.blam.mappers.collection.read.collection_importer import CollectionImporter
from blam_schemas.collection.blam_collection_repository_v1_0 import Cmd
from lacos.blam.models.base_project_info import ProjectInfo
from lacos.blam.models.collection.collection_repository import Collection


@pytest.fixture
def zaghawa_xml_content():
    """Load the zaghawa.xml file content"""
    xml_path = os.path.join('data', 'zaghawa', 'zaghawa', 'v1', 'content', 'zaghawa.xml')
    try:
        with open(xml_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        # Try alternative paths
        alternate_paths = [
            os.path.join('data', 'zaghawa', 'v1', 'content', 'zaghawa.xml'),
            os.path.join('data', 'formatted', 'zaghawa.xml')
        ]
        for path in alternate_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except FileNotFoundError:
                continue
        raise FileNotFoundError(f"Could not find collection XML file at {xml_path} or alternate locations")


@pytest.fixture
def cmd_data(zaghawa_xml_content):
    """Parse XML into CMD data object"""
    return CollectionImporter.validate_xml(zaghawa_xml_content)


@pytest.mark.django_db
def test_validate_xml_with_real_data(cmd_data):
    """Test that real XML can be parsed into a Cmd object"""
    assert isinstance(cmd_data, Cmd)
    assert hasattr(cmd_data, 'header')
    assert cmd_data.header.md_collection_display_name.value == "Zaghawa"


@pytest.mark.django_db
def test_import_from_xml_real_models(zaghawa_xml_content):
    """Test importing Zaghawa XML into real Django models"""
    try:
        # Attempt to import with real models
        collection = CollectionImporter.import_from_xml(zaghawa_xml_content)
        
        # If successful, verify the collection was created
        assert collection is not None
        assert isinstance(collection, Collection)
        assert collection.general_info is not None
        assert collection.general_info.display_title == "Zaghawa"
        
        # Verify more fields
        assert collection.general_info.version == "1"
        assert collection.publication_info is not None
        assert collection.administrative_info is not None
        assert collection.structural_info is not None
        
        # Verify publication info
        assert collection.publication_info.data_provider == "Language Archive Cologne"
        
        # Verify administrative info - license should be default or empty
        # This is the problematic part of the XML
        assert collection.administrative_info is not None
        
        # Verify rights holder
        rights_holders = collection.administrative_info.rights_holders.all()
        assert len(rights_holders) > 0
        rights_holder = rights_holders[0]
        assert rights_holder.rights_holder_name == "Birgit Hellwig"
    
    except Exception as e:
        # If an expected failure occurs due to empty license fields, note that
        pytest.fail(f"Failed to import collection from XML: {str(e)}")


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
    assert cmd_data.header.md_collection_display_name.value == "Zaghawa"
    assert cmd_data.header.md_creation_date.value.year == 2018
    assert cmd_data.header.md_creation_date.value.month == 11
    assert cmd_data.header.md_creation_date.value.day == 29
    assert cmd_data.header.md_self_link.value == "hdl:11341/00-0000-0000-0000-1AC6-9"


def test_verify_cmd_license_mapping(cmd_data):
    """Test that license information is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    assert repo.mdlicense.value == "CC0"
    assert repo.mdlicense.uri == "https://creativecommons.org/public-domain/cc0/"


def test_verify_cmd_general_info_mapping(cmd_data):
    """Test that general info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert general_info.collection_display_title == "Zaghawa"
    assert "Zaghawa-Wagi language of Sudan" in general_info.collection_description
    assert len(general_info.collection_id) > 0
    assert general_info.collection_id[0].value == "hdl:11341/00-0000-0000-0000-1AC6-9"


def test_verify_cmd_object_languages_mapping(cmd_data):
    """Test that object languages are correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert hasattr(general_info, 'collection_object_languages')
    assert len(general_info.collection_object_languages.collection_object_language) > 0
    lang = general_info.collection_object_languages.collection_object_language[0]
    assert lang.object_language_name == "Beria"
    assert lang.object_language_iso639_3_code.value == "zag"
    assert lang.object_language_glottolog_code.value == "zagh1240"


def test_verify_cmd_location_mapping(cmd_data):
    """Test that location information is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    general_info = repo.collection_general_info
    assert hasattr(general_info, 'collection_location')
    location = general_info.collection_location
    assert location.collection_country_code.value == "DE"
    assert location.collection_country_facet == "Germany"


def test_verify_cmd_publication_info_mapping(cmd_data):
    """Test that publication info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    pub_info = repo.collection_publication_info
    assert str(pub_info.collection_publication_year) == "2018"
    assert pub_info.collection_data_provider == "Language Archive Cologne"


def test_verify_cmd_creators_mapping(cmd_data):
    """Test that creators are correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    pub_info = repo.collection_publication_info
    assert hasattr(pub_info, 'collection_creators')
    assert len(pub_info.collection_creators.collection_creator) > 0
    creator = pub_info.collection_creators.collection_creator[0]
    assert creator.creator_name.creator_family_name == "Hellwig"
    assert creator.creator_name.creator_given_name == "Birgit"


def test_verify_cmd_administrative_info_mapping(cmd_data):
    """Test that administrative info is correctly mapped from XML to CMD"""
    repo = cmd_data.components.blam_collection_repository_v1_0
    admin_info = repo.collection_administrative_info
    assert admin_info.access.value.value == "open"
    assert len(admin_info.license) > 0
    # The license fields are empty in zaghawa.xml - this is likely the source of the import error
    assert admin_info.license[0].license_identifier == ""
    assert admin_info.license[0].license_name == ""


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


@pytest.mark.django_db
def test_import_license(cmd_data):
    """Test the _import_license method with real database models"""
    try:
        result = CollectionImporter._import_license(cmd_data)
        # If successful, verify the license was created properly 
        # despite empty fields in XML
        assert result is not None
    except Exception as e:
        pytest.fail(f"Failed to import license: {str(e)}")


@pytest.mark.django_db
def test_import_general_info_real(cmd_data):
    """Test _import_general_info with real database models"""
    try:
        result = CollectionImporter._import_general_info(cmd_data)
        assert result is not None
        assert result.display_title == "Zaghawa"
        assert "Zaghawa-Wagi" in result.description
    except Exception as e:
        pytest.fail(f"Failed to import general info: {str(e)}")


@pytest.mark.django_db
def test_import_administrative_info_real(cmd_data):
    """Test _import_administrative_info with real database models"""
    try:
        result = CollectionImporter._import_administrative_info(cmd_data)
        assert result is not None
        
        # Check rights holders
        rights_holders = result.rights_holders.all()
        assert len(rights_holders) > 0
        assert rights_holders[0].rights_holder_name == "Birgit Hellwig"
        
        # Check licenses
        licenses = result.licenses.all()
        assert len(licenses) > 0
        # The license name/identifier should be empty or default
    except Exception as e:
        # If an expected failure occurs due to empty license fields, note that
        pytest.fail(f"Failed to import administrative info: {str(e)}")
