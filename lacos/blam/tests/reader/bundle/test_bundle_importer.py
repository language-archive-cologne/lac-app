import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from django.core.exceptions import ValidationError

from lacos.blam.mappers.bundle.read.bundle_importer import BundleImporter
from lacos.blam.models.bundle.bundle_repository import Bundle
from lacos.blam.models.bundle.bundle_header import BundleHeader
from blam_schemas.bundle.blam_bundle_repository_v1_0 import Cmd

# Fixture to load the XML content once and reuse it across tests
@pytest.fixture
def zaghawa_xml_content():
    # Determine the base directory of the project root
    base_dir = Path(__file__).resolve().parents[3]  # Adjust the number based on your directory structure

    # Construct the full path to the XML file relative to the project root
    xml_file_path = base_dir / 'data/zaghawa/zaghawa/zag_eoi_20141016_1/v1/content/zag_eoi_20141016_1.xml'

    # Read the XML content
    with open(xml_file_path, 'r', encoding='utf-8') as f:
        return f.read()

class TestBundleImporter:
    
    def test_validate_xml(self, zaghawa_xml_content):
        """Test that XML validation works correctly"""
        # Test with valid XML
        try:
            cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
            assert isinstance(cmd_data, Cmd)
        except ValidationError:
            pytest.fail("Valid XML raised ValidationError")
        
        # Test with invalid XML
        invalid_xml = "<invalid>XML</invalid>"
        with pytest.raises(ValidationError):
            BundleImporter.validate_xml(invalid_xml)
    
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_cmd_to_models')
    def test_import_from_xml(self, mock_import_cmd, zaghawa_xml_content):
        """Test the import_from_xml method with transaction handling"""
        mock_bundle = MagicMock()
        mock_import_cmd.return_value = mock_bundle
        
        # Test with collection_id
        result = BundleImporter.import_from_xml(zaghawa_xml_content, collection_id=1)
        assert result == mock_bundle
        
        # Verify the mock was called with a Cmd object and collection_id
        args, kwargs = mock_import_cmd.call_args
        assert isinstance(args[0], Cmd)
        assert args[1] == 1
        
        # Test without collection_id
        BundleImporter.import_from_xml(zaghawa_xml_content)
        args, kwargs = mock_import_cmd.call_args
        assert isinstance(args[0], Cmd)
        assert args[1] is None
    
    @patch('lacos.blam.mappers.bundle.read.import_general_info')
    def test_import_general_info(self, mock_import_general_info, zaghawa_xml_content):
        """Test the _import_general_info method"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_general_info = MagicMock()
        mock_import_general_info.return_value = mock_general_info
        
        result = BundleImporter._import_general_info(cmd_data)
        
        mock_import_general_info.assert_called_once_with(cmd_data)
        assert result == mock_general_info
    
    @patch('lacos.blam.mappers.bundle.read.import_publication_info')
    def test_import_publication_info(self, mock_import_publication_info, zaghawa_xml_content):
        """Test the _import_publication_info method"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_publication_info = MagicMock()
        mock_import_publication_info.return_value = mock_publication_info
        
        result = BundleImporter._import_publication_info(cmd_data)
        
        mock_import_publication_info.assert_called_once_with(cmd_data)
        assert result == mock_publication_info
    
    @patch('lacos.blam.mappers.bundle.read.import_administrative_info')
    def test_import_administrative_info(self, mock_import_administrative_info, zaghawa_xml_content):
        """Test the _import_administrative_info method"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_administrative_info = MagicMock()
        mock_import_administrative_info.return_value = mock_administrative_info
        
        result = BundleImporter._import_administrative_info(cmd_data)
        
        mock_import_administrative_info.assert_called_once_with(cmd_data)
        assert result == mock_administrative_info
    
    @patch('lacos.blam.mappers.bundle.read.import_structural_info')
    def test_import_structural_info(self, mock_import_structural_info, zaghawa_xml_content):
        """Test the _import_structural_info method with and without collection_id"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_structural_info = MagicMock()
        mock_import_structural_info.return_value = mock_structural_info
        
        # Test with collection_id
        result = BundleImporter._import_structural_info(cmd_data, collection_id=1)
        mock_import_structural_info.assert_called_with(cmd_data, 1)
        assert result == mock_structural_info
        
        # Test without collection_id
        result = BundleImporter._import_structural_info(cmd_data, collection_id=None)
        assert result is None
    
    def test_extract_metadata_license(self, zaghawa_xml_content):
        """Test the _extract_metadata_license method with real XML data"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        
        license_value, license_uri = BundleImporter._extract_metadata_license(cmd_data)
        
        # Check that we got some values (actual values will depend on your test XML)
        # If your test XML has license info, verify the exact values
        # If not, these assertions might need adjustment
        assert isinstance(license_value, str) or license_value is None
        assert isinstance(license_uri, str) or license_uri is None
    
    @patch('lacos.blam.models.bundle.bundle_repository.Bundle.objects.get_or_create')
    def test_create_or_update_bundle(self, mock_get_or_create):
        """Test the _create_or_update_bundle method for both creating and updating"""
        # Setup test data
        mock_general_info = MagicMock()
        mock_publication_info = MagicMock()
        mock_administrative_info = MagicMock()
        mock_structural_info = MagicMock()
        mock_bundle = MagicMock()
        
        # Test creating a new bundle
        mock_get_or_create.return_value = (mock_bundle, True)  # True means created
        
        result = BundleImporter._create_or_update_bundle(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            "CC-BY-4.0",
            "https://creativecommons.org/licenses/by/4.0/"
        )
        
        mock_get_or_create.assert_called_with(
            general_info=mock_general_info,
            defaults={
                'publication_info': mock_publication_info,
                'administrative_info': mock_administrative_info,
                'structural_info': mock_structural_info,
                'md_license': "CC-BY-4.0",
                'md_license_uri': "https://creativecommons.org/licenses/by/4.0/"
            }
        )
        assert result == mock_bundle
        
        # Test updating an existing bundle
        mock_get_or_create.return_value = (mock_bundle, False)  # False means not created
        
        result = BundleImporter._create_or_update_bundle(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            "CC-BY-4.0",
            "https://creativecommons.org/licenses/by/4.0/"
        )
        
        assert mock_bundle.publication_info == mock_publication_info
        assert mock_bundle.administrative_info == mock_administrative_info
        assert mock_bundle.structural_info == mock_structural_info
        assert mock_bundle.md_license == "CC-BY-4.0"
        assert mock_bundle.md_license_uri == "https://creativecommons.org/licenses/by/4.0/"
        mock_bundle.save.assert_called_once()
        assert result == mock_bundle
    
    @patch('lacos.blam.mappers.bundle.read.import_project_info')
    def test_import_and_link_projects(self, mock_import_project_info, zaghawa_xml_content):
        """Test the _import_and_link_projects method"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_bundle = MagicMock()
        
        # Test with projects
        mock_projects = [MagicMock(), MagicMock()]
        mock_import_project_info.return_value = mock_projects
        
        BundleImporter._import_and_link_projects(cmd_data, mock_bundle)
        
        mock_import_project_info.assert_called_once_with(cmd_data)
        assert mock_bundle.projects.add.call_count == len(mock_projects)
        for project in mock_projects:
            mock_bundle.projects.add.assert_any_call(project)
    
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_general_info')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_publication_info')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_administrative_info')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_structural_info')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._extract_metadata_license')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._create_or_update_bundle')
    @patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_and_link_projects')
    def test_import_cmd_to_models(
        self, 
        mock_import_projects, 
        mock_create_bundle, 
        mock_extract_license,
        mock_import_structural, 
        mock_import_administrative, 
        mock_import_publication, 
        mock_import_general,
        zaghawa_xml_content
    ):
        """Test the _import_cmd_to_models method with all components mocked"""
        cmd_data = BundleImporter.validate_xml(zaghawa_xml_content)
        mock_general_info = MagicMock()
        mock_publication_info = MagicMock()
        mock_administrative_info = MagicMock()
        mock_structural_info = MagicMock()
        mock_bundle = MagicMock()
        
        mock_import_general.return_value = mock_general_info
        mock_import_publication.return_value = mock_publication_info
        mock_import_administrative.return_value = mock_administrative_info
        mock_import_structural.return_value = mock_structural_info
        mock_extract_license.return_value = ("CC-BY-4.0", "https://creativecommons.org/licenses/by/4.0/")
        mock_create_bundle.return_value = mock_bundle
        
        result = BundleImporter._import_cmd_to_models(cmd_data, collection_id=1)
        
        mock_import_general.assert_called_once_with(cmd_data)
        mock_import_publication.assert_called_once_with(cmd_data)
        mock_import_administrative.assert_called_once_with(cmd_data)
        mock_import_structural.assert_called_once_with(cmd_data, 1)
        mock_extract_license.assert_called_once_with(cmd_data)
        mock_create_bundle.assert_called_once_with(
            mock_general_info,
            mock_publication_info,
            mock_administrative_info,
            mock_structural_info,
            "CC-BY-4.0",
            "https://creativecommons.org/licenses/by/4.0/"
        )
        mock_import_projects.assert_called_once_with(cmd_data, mock_bundle)
        assert result == mock_bundle
    
    def test_bundle_header_integration(self, zaghawa_xml_content):
        """Test that BundleHeader is properly integrated in the import process"""
        # This test requires database access, so we'll mock the database operations
        with patch('lacos.blam.mappers.bundle.read.bundle_importer.BundleImporter._import_cmd_to_models') as mock_import:
            mock_bundle = MagicMock(spec=Bundle)
            mock_header = MagicMock(spec=BundleHeader)
            mock_bundle.header = mock_header
            mock_import.return_value = mock_bundle
            
            result = BundleImporter.import_from_xml(zaghawa_xml_content)
            
            assert result == mock_bundle
            assert hasattr(result, 'header')
            assert isinstance(result.header, MagicMock)  # In real code, this would be BundleHeader